"""Native ADK runtime-skill coverage, not live-model or procedure qualification."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from google.adk.tools.skill_toolset import SkillToolset

from corsair.adapters.inference.adk import run_auditor, run_producer
from corsair.adapters.scm.local import StoredSourceReader
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.agents.auditor.contracts import AuditResult as RoleAuditResult
from corsair.agents.auditor.toolsets import build_auditor_toolset
from corsair.agents.producer.contracts import ProducerDecision as RoleProducerDecision
from corsair.agents.producer.toolsets import build_producer_toolset
from corsair.agents.resources import load_runtime_skills
from corsair.contracts import AuditInput, AuditResult, ProducerDecision
from corsair.settings import ModelSettings
from tests.unit.adk import ScriptedLlm, text_response, tool_response
from tests.unit.test_agents import _producer_input, _proposal_args, _submit_args


def _audit_input(store: ArtifactStore) -> AuditInput:
    prepared = _producer_input(store).prepared
    from corsair.contracts import Submission

    return AuditInput(
        finding=prepared.finding,
        recipe=prepared.recipe,
        source_excerpt=prepared.source_excerpt,
        submission=Submission(**_submit_args()),
        max_output_tokens=512,
    )


def _tool_response(model: ScriptedLlm, name: str) -> dict:
    for request in model.requests:
        for content in request.contents:
            for part in content.parts:
                response = part.function_response
                if response is not None and response.name == name:
                    return dict(response.response or {})
    raise AssertionError(f"native {name!r} response was not retained in the episode")


def test_role_contract_re_exports_are_the_canonical_models(tmp_path: Path):
    store = ArtifactStore(tmp_path)

    assert RoleProducerDecision is ProducerDecision
    assert RoleAuditResult is AuditResult
    producer_tools = build_producer_toolset(_producer_input(store), StoredSourceReader(store))
    producer_names = [getattr(tool, "__name__", None) for tool in producer_tools[:-1]]
    assert producer_names == ["read_file", "list_files", "preview_invocation", "relative_path"]
    producer_loader = producer_tools[-1]
    assert isinstance(producer_loader, SkillToolset)
    assert [skill.name for skill in producer_loader.skills] == ["source-grounding"]
    auditor_tools = build_auditor_toolset()
    assert [skill.name for skill in auditor_tools[0].skills] == ["semantic-review"]


@pytest.mark.asyncio
async def test_producer_native_load_skill_then_schema_completion_counts_real_calls(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    store = ArtifactStore(tmp_path)
    model = ScriptedLlm(
        model="scripted-runtime-skill",
        structured_tools=False,
        responses=[
            tool_response("load_skill", {"skill_name": "source-grounding"}),
            tool_response("set_model_response", _proposal_args()),
        ],
    )

    caplog.set_level(logging.INFO, logger="corsair")
    output = await run_producer(_producer_input(store), ModelSettings(), store, model)

    assert output.feedback is None
    assert output.decision is not None
    assert output.usage.llm_calls == output.usage.tool_calls == 2
    assert output.usage.skills_loaded == ["source-grounding"]
    assert "set_model_response" in model.requests[1].tools_dict
    assert {"load_skill", "load_skill_resource"} <= set(model.requests[0].tools_dict)
    assert not {
        "list_skills",
        "search_skills",
        "run_skill_script",
        "unload_skill",
    } & set(model.requests[0].tools_dict)
    assert any(
        record.message == "agent.skill_loaded"
        and getattr(record, "fields", {}) == {"role": "producer", "skill_name": "source-grounding"}
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_resource_loader_rejects_another_roles_skill_without_claiming_load(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    model = ScriptedLlm(
        model="scripted-cross-role-resource",
        responses=[
            tool_response(
                "load_skill_resource",
                {"skill_name": "semantic-review", "file_path": "references/review.md"},
            ),
            text_response(json.dumps(_proposal_args())),
        ],
    )

    output = await run_producer(_producer_input(store), ModelSettings(), store, model)

    assert output.feedback is None and output.decision is not None
    assert output.usage.llm_calls == 2 and output.usage.tool_calls == 1
    assert output.usage.skills_loaded == []
    assert _tool_response(model, "load_skill_resource")["error_code"] == "SKILL_NOT_FOUND"
    assert "run_skill_script" not in model.requests[0].tools_dict


@pytest.mark.asyncio
async def test_auditor_native_load_skill_is_bounded_and_remains_source_free(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    model = ScriptedLlm(
        model="scripted-auditor-runtime-skill",
        responses=[
            tool_response("load_skill", {"skill_name": "semantic-review"}),
            text_response(
                json.dumps(
                    {
                        "decision": "ACCEPT",
                        "rule": "source-grounded-fixture",
                        "reason": "The paired payloads exercise the configured seam.",
                    }
                )
            ),
        ],
    )

    output = await run_auditor(_audit_input(store), ModelSettings(), model)

    assert output.feedback is None and output.review is not None
    assert output.usage.llm_calls == 2 and output.usage.tool_calls == 1
    assert output.usage.skills_loaded == ["semantic-review"]
    assert set(model.requests[0].tools_dict) == {"load_skill", "load_skill_resource"}
    assert "read_file" not in model.requests[0].tools_dict
    assert "list_files" not in model.requests[0].tools_dict


@pytest.mark.asyncio
async def test_runtime_skill_loads_are_fresh_for_each_native_producer_episode(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    model = ScriptedLlm(
        model="scripted-fresh-skills",
        responses=[
            tool_response("load_skill", {"skill_name": "source-grounding"}),
            text_response(json.dumps(_proposal_args())),
            tool_response("load_skill", {"skill_name": "source-grounding"}),
            text_response(json.dumps(_proposal_args())),
        ],
    )
    producer_input = _producer_input(store)

    first = await run_producer(producer_input, ModelSettings(), store, model)
    second = await run_producer(producer_input, ModelSettings(), store, model)

    assert first.feedback is second.feedback is None
    assert first.usage.skills_loaded == second.usage.skills_loaded == ["source-grounding"]
    assert len(model.requests) == 4
    assert not any(
        part.function_response and part.function_response.name == "load_skill"
        for content in model.requests[2].contents
        for part in content.parts
    )


@pytest.mark.asyncio
async def test_runtime_skill_loader_cap_stops_a_fifth_native_load_without_widening_budget(
    tmp_path: Path,
):
    store = ArtifactStore(tmp_path)
    base = _producer_input(store)
    producer_input = base.model_copy(
        update={
            "budget": base.budget.model_copy(update={"episode_llm_calls": 6, "max_tool_calls": 6}),
            "llm_call_limit": 6,
            "tool_call_limit": 6,
        }
    )
    model = ScriptedLlm(
        model="scripted-loader-cap",
        responses=[
            tool_response("load_skill", {"skill_name": "source-grounding"}) for _ in range(5)
        ],
    )

    output = await run_producer(producer_input, ModelSettings(), store, model)

    assert output.decision is None
    assert output.feedback is not None
    assert "runtime skill loader budget" in output.feedback.reason
    assert output.usage.llm_calls == 5
    assert output.usage.tool_calls == 4
    assert output.usage.skills_loaded == ["source-grounding"]


def test_role_local_skills_expose_only_text_and_admitted_names():
    producer = load_runtime_skills("producer")
    auditor = load_runtime_skills("auditor")

    assert [skill.name for skill in producer] == ["source-grounding"]
    assert [skill.name for skill in auditor] == ["semantic-review"]
    for skill in [*producer, *auditor]:
        assert skill.frontmatter.metadata == {}
        assert skill.frontmatter.allowed_tools is None
        assert skill.resources.assets == {}
        assert skill.resources.scripts == {}
        assert all(isinstance(content, str) for content in skill.resources.references.values())
