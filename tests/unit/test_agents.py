from __future__ import annotations

import io
import json
import tarfile
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from google.adk.tools.skill_toolset import SkillToolset
from google.adk.tools.tool_context import ToolContext

from corsair.adapters.inference.adk import (
    _auditor_prompt,
    _producer_prompt,
    run_auditor,
    run_producer,
)
from corsair.adapters.scm.local import StoredSourceReader
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.agents.auditor.factory import build_auditor
from corsair.agents.auditor.toolsets import build_auditor_toolset
from corsair.agents.producer.factory import build_producer
from corsair.agents.producer.toolsets import build_producer_toolset
from corsair.agents.resources import load_runtime_skills
from corsair.contracts import (
    AuditInput,
    AuditResult,
    Budget,
    Finding,
    NoGroundedCandidate,
    PlanRevision,
    PreparedCase,
    ProducerDecision,
    ProducerInput,
    ProducerOutput,
    ProducerProposal,
    PythonRecipe,
    RunManifest,
    Submission,
)
from corsair.settings import ModelSettings
from tests.unit.adk import (
    ScriptedLlm,
    text_response,
    tool_batch_response,
    tool_response,
)


def _archive(files: dict[str, str]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name, text in files.items():
            data = text.encode()
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return output.getvalue()


def _prepared(store: ArtifactStore) -> PreparedCase:
    source = store.put(
        _archive(
            {
                "target.py": "def disclose(payload, *, prefix):\n    return prefix + payload\n",
                "note.txt": "admitted public source\n",
            }
        ),
        "application/x-tar",
    )
    private = store.put(b"PRIVATE_RANDOM_SECRET_DO_NOT_PROMPT")
    return PreparedCase(
        case_id="case",
        finding=Finding(
            title="payload may be disclosed",
            description="The configured callable may return untrusted payload input.",
            file="target.py",
            line=2,
        ),
        recipe=PythonRecipe(
            module_file="target.py",
            function="disclose",
            payload_parameter="payload",
            fixed_kwargs={"prefix": "prefix:"},
        ),
        source=source,
        fixed_source=private,
        source_excerpt="def disclose(payload, *, prefix):\n    return prefix + payload\n",
        manifest=RunManifest(
            package_version="test",
            request_digest="0" * 64,
            config_digest="1" * 64,
            producer_prompt_digest="2" * 64,
            auditor_prompt_digest="3" * 64,
            image_id="TRUSTED_ORACLE_CASE_PATH_DO_NOT_PROMPT",
            models={"producer": "test", "auditor": "test"},
        ),
    )


def _producer_input(store: ArtifactStore, *, tool_call_limit: int = 3) -> ProducerInput:
    return ProducerInput(
        run_id="run",
        prepared=_prepared(store),
        budget=Budget(episode_llm_calls=2, max_tool_calls=3, max_output_tokens=512),
        round_index=1,
        llm_call_limit=2,
        tool_call_limit=tool_call_limit,
    )


def _submit_args(*, revision: int = 1, parent_revision: int | None = None) -> dict:
    return {
        "control_payload": "hello",
        "exploit_payload": "adversarial",
        "hypothesis": "The callable returns its payload after applying the fixed prefix.",
        "plan": {
            "revision": revision,
            "parent_revision": parent_revision,
            "objective": "propose a declarative payload pair",
            "next_steps": ["submit the payload pair"],
            "reason": "the admitted return statement includes payload",
        },
    }


def _proposal_args(*, revision: int = 1, parent_revision: int | None = None) -> dict:
    return {
        "schema_version": "corsair.producer-decision/1",
        "kind": "proposal",
        "submission": _submit_args(revision=revision, parent_revision=parent_revision),
    }


def _abstention_args() -> dict:
    return {
        "schema_version": "corsair.producer-decision/1",
        "kind": "no_grounded_candidate",
        "reason": "The admitted source does not ground an allowed payload candidate.",
    }


@pytest.mark.asyncio
async def test_producer_uses_native_structured_output_and_completes_after_one_response(
    tmp_path: Path,
):
    store = ArtifactStore(tmp_path)
    producer_input = _producer_input(store)
    model = ScriptedLlm(
        model="scripted",
        responses=[
            text_response(json.dumps(_proposal_args())),
            text_response("this must never receive a second request"),
        ],
    )

    output = await run_producer(producer_input, ModelSettings(), store, model)

    assert output.decision is not None
    assert isinstance(output.decision.root, ProducerProposal)
    assert output.submission_for_verification() is not None
    assert output.feedback is None
    assert output.usage.llm_calls == 1
    assert output.usage.tool_calls == 0
    assert isinstance(output.decision.root.submission.plan, PlanRevision)
    assert model.requests[0].config.response_schema is ProducerDecision
    assert len(model.requests) == 1
    assert model.requests[0].config.max_output_tokens == 512


@pytest.mark.asyncio
async def test_adk_native_schema_tool_completion_is_counted_and_validated(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    model = ScriptedLlm(
        model="scripted-schema-tool",
        structured_tools=False,
        responses=[tool_response("set_model_response", _abstention_args())],
    )
    output = await run_producer(_producer_input(store), ModelSettings(), store, model)
    assert output.feedback is None
    assert output.decision is not None
    assert isinstance(output.decision.root, NoGroundedCandidate)
    assert output.submission_for_verification() is None
    assert output.usage.llm_calls == output.usage.tool_calls == 1
    assert "set_model_response" in model.requests[0].tools_dict


@pytest.mark.asyncio
async def test_tool_cap_is_charged_before_work_and_source_path_escape_is_rejected(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    producer_input = _producer_input(store, tool_call_limit=1)
    tools = build_producer_toolset(producer_input, StoredSourceReader(store))
    read_file = tools[0]
    assert isinstance(read_file, Callable)
    escaped = await read_file("../private.txt", cast(ToolContext, object()))
    assert "normalized relative" in escaped["error"]
    model = ScriptedLlm(
        model="scripted-tool-limit",
        responses=[tool_batch_response([("list_files", {}), ("read_file", {"path": "target.py"})])],
    )
    output = await run_producer(producer_input, ModelSettings(), store, model)
    assert output.decision is None
    assert output.feedback is not None and "tool-call budget" in output.feedback.reason
    assert output.usage.tool_calls == 1
    assert len(model.requests) == 1


def test_factories_share_canonical_pydantic_output_models(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    tools = build_producer_toolset(_producer_input(store), StoredSourceReader(store))
    producer = build_producer("gemini-2.5-flash", tools=tools)
    auditor_tools = build_auditor_toolset()
    auditor = build_auditor("gemini-2.5-flash", auditor_tools)

    assert producer.name == "producer"
    tool_names = []
    for tool in producer.tools[:2]:
        assert callable(tool)
        name = getattr(tool, "__name__", None)
        assert isinstance(name, str)
        tool_names.append(name)
    assert tool_names == ["read_file", "list_files"]
    producer_loader = producer.tools[2]
    auditor_loader = auditor.tools[0]
    assert isinstance(producer_loader, SkillToolset)
    assert isinstance(auditor_loader, SkillToolset)
    assert [skill.name for skill in producer_loader.skills] == ["source-grounding"]
    assert [skill.name for skill in auditor_loader.skills] == ["semantic-review"]
    assert auditor.include_contents == "none"
    assert auditor.output_schema is AuditResult
    assert producer.output_schema is ProducerDecision
    schema = ProducerDecision.model_json_schema()
    assert schema["discriminator"]["propertyName"] == "kind"
    assert len(schema["oneOf"]) == 2
    proposal = schema["$defs"]["ProducerProposal"]
    assert proposal["properties"]["kind"]["const"] == "proposal"
    assert "submission" in proposal["required"]
    assert {"control_payload", "exploit_payload", "hypothesis", "plan"} <= set(
        schema["$defs"]["Submission"]["required"]
    )
    assert schema["$defs"]["PlanRevision"]["additionalProperties"] is False
    with pytest.raises(ValueError, match="exactly one native SkillToolset"):
        build_producer("gemini-2.5-flash", tools[:-1])


def test_producer_output_uses_decisions_and_decodes_predecision_activity_data():
    submission = Submission(**_submit_args())
    decision = ProducerDecision(root=ProducerProposal(submission=submission))

    current = ProducerOutput(decision=decision)
    historical = ProducerOutput.model_validate({"submission": submission.model_dump()})

    assert current.submission_for_verification() == submission
    assert historical.decision is None
    assert historical.submission_for_verification() == submission
    with pytest.raises(ValueError, match="both a decision and a submission"):
        ProducerOutput(decision=decision, submission=submission)


@pytest.mark.asyncio
async def test_invalid_plan_parent_is_typed_producer_data_not_a_provider_retry(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    producer_input = _producer_input(store)
    model = ScriptedLlm(
        model="scripted",
        responses=[text_response(json.dumps(_proposal_args(revision=2, parent_revision=1)))],
    )

    output = await run_producer(producer_input, ModelSettings(), store, model)

    assert output.decision is None
    assert output.feedback is not None
    assert output.feedback.gate == "producer_invalid"
    assert output.feedback.operational is False
    assert len(model.requests) == 1


@pytest.mark.asyncio
async def test_auditor_is_fresh_tool_free_one_request_and_rejects_malformed_output(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    prepared = _prepared(store)
    audit_input = AuditInput(
        finding=prepared.finding,
        recipe=prepared.recipe,
        source_excerpt=prepared.source_excerpt,
        submission=Submission(**_submit_args()),
        max_output_tokens=512,
    )
    model = ScriptedLlm(model="scripted", responses=[text_response("not an AuditResult")])

    output = await run_auditor(audit_input, ModelSettings(), model)

    assert output.review is None
    assert output.feedback is not None
    assert output.feedback.gate == "audit_invalid"
    assert output.feedback.operational is False
    assert output.usage.llm_calls == 1
    assert len(model.requests) == 1
    assert model.requests[0].config.max_output_tokens == 512


def test_role_prompts_exclude_oracles_case_paths_private_secret_and_audit_outcomes(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    producer_input = _producer_input(store)
    producer_packet = _producer_prompt(producer_input)
    audit_packet = _auditor_prompt(
        AuditInput(
            finding=producer_input.prepared.finding,
            recipe=producer_input.prepared.recipe,
            source_excerpt=producer_input.prepared.source_excerpt,
            submission=Submission(**_submit_args()),
            max_output_tokens=512,
        )
    )

    assert "PRIVATE_RANDOM_SECRET_DO_NOT_PROMPT" not in producer_packet
    assert "TRUSTED_ORACLE_CASE_PATH_DO_NOT_PROMPT" not in producer_packet
    assert "TRUSTED_ORACLE_CASE_PATH_DO_NOT_PROMPT" not in audit_packet
    assert "fixed_source" not in producer_packet
    assert "outcome" not in audit_packet.lower().split("packet only.", maxsplit=1)[1]
    producer_document = json.loads(model_text := producer_packet.split("\n", maxsplit=1)[1])
    assert "case_id" not in producer_document
    assert "manifest" not in producer_document
    assert producer_document["round"] == {
        "parent_revision": None,
        "revision": 1,
    }
    assert model_text


@pytest.mark.parametrize(
    "invalid_field", ["string_plan", "unknown_field", "missing_plan", "parent"]
)
@pytest.mark.asyncio
async def test_structured_producer_rejects_invalid_or_stale_proposals(tmp_path, invalid_field):
    store = ArtifactStore(tmp_path)
    args = _proposal_args()
    if invalid_field == "string_plan":
        args["submission"]["plan"] = json.dumps(args["submission"]["plan"])
    elif invalid_field == "unknown_field":
        args["submission"]["plan"]["unapproved"] = "must not be admitted"
    elif invalid_field == "missing_plan":
        del args["submission"]["plan"]
    else:
        args["submission"]["plan"]["parent_revision"] = 1
    model = ScriptedLlm(
        model="scripted-invalid-schema", responses=[text_response(json.dumps(args))]
    )
    output = await run_producer(_producer_input(store), ModelSettings(), store, model)
    assert output.decision is None
    assert output.feedback is not None and output.feedback.gate == "producer_invalid"
    assert output.feedback.operational is False
    assert "must not be admitted" not in output.feedback.reason
    assert output.usage.llm_calls == 1
    assert output.usage.tool_calls == 0


@pytest.mark.asyncio
async def test_source_inspection_then_structured_completion_share_one_native_episode(tmp_path):
    store = ArtifactStore(tmp_path)
    model = ScriptedLlm(
        model="scripted-source-then-schema",
        responses=[
            tool_response("read_file", {"path": "target.py"}),
            text_response(json.dumps(_proposal_args())),
        ],
    )
    output = await run_producer(_producer_input(store), ModelSettings(), store, model)
    assert output.feedback is None and output.submission_for_verification() is not None
    assert output.usage.llm_calls == 2 and output.usage.tool_calls == 1
    assert all(request.config.response_schema is ProducerDecision for request in model.requests)
    assert all(
        set(request.tools_dict) == {"read_file", "list_files", "load_skill", "load_skill_resource"}
        for request in model.requests
    )


@pytest.mark.asyncio
async def test_core_procedure_reaches_first_model_request_without_inventing_tool_calls(tmp_path):
    store = ArtifactStore(tmp_path)
    producer_model = ScriptedLlm(
        model="scripted", responses=[text_response(json.dumps(_proposal_args()))]
    )
    produced = await run_producer(_producer_input(store), ModelSettings(), store, producer_model)
    assert produced.usage.skills_preloaded == ["source-grounding"]
    assert produced.usage.skills_loaded == []
    assert produced.usage.tool_calls == 0
    assert "Runtime procedure: source-grounding" in str(
        producer_model.requests[0].config.system_instruction
    )
    assert load_runtime_skills("producer")[0].instructions in str(
        producer_model.requests[0].config.system_instruction
    )
    audit_model = ScriptedLlm(
        model="scripted",
        responses=[
            text_response('{"decision":"INSUFFICIENT_CONTEXT","reason":"insufficient source"}')
        ],
    )
    prepared = _prepared(store)
    audited = await run_auditor(
        AuditInput(
            finding=prepared.finding,
            recipe=prepared.recipe,
            source_excerpt=prepared.source_excerpt,
            submission=Submission(**_submit_args()),
            max_output_tokens=512,
        ),
        ModelSettings(),
        audit_model,
    )
    assert audited.usage.skills_preloaded == ["semantic-review"]
    assert audited.usage.skills_loaded == []
    assert audited.usage.tool_calls == 0
    assert "Runtime procedure: semantic-review" in str(
        audit_model.requests[0].config.system_instruction
    )
