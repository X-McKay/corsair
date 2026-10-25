from __future__ import annotations

import importlib.util
import io
import json
import tarfile
from pathlib import Path

import pytest
from google.adk.tools.function_tool import FunctionTool

from corsair.agents.auditor.factory import build_auditor
from corsair.agents.producer.factory import build_producer
from corsair.agents.producer.tools import build_producer_tools
from corsair.contracts import (
    AuditInput,
    Budget,
    Finding,
    PreparedCase,
    ProducerInput,
    PythonRecipe,
    RunManifest,
    Submission,
)
from corsair.runtime.agent_runner import (
    _auditor_prompt,
    _producer_prompt,
    run_auditor,
    run_producer,
)
from corsair.runtime.artifacts import ArtifactStore
from corsair.settings import ModelSettings

_fixture_spec = importlib.util.spec_from_file_location(
    "corsair_test_adk_fixture", Path(__file__).parents[1] / "fixtures" / "adk.py"
)
assert _fixture_spec is not None and _fixture_spec.loader is not None
_fixture_module = importlib.util.module_from_spec(_fixture_spec)
_fixture_spec.loader.exec_module(_fixture_module)
ScriptedLlm = _fixture_module.ScriptedLlm
text_response = _fixture_module.text_response
tool_batch_response = _fixture_module.tool_batch_response
tool_response = _fixture_module.tool_response


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


def _producer_input(store: ArtifactStore, **overrides) -> ProducerInput:
    values = {
        "run_id": "run",
        "prepared": _prepared(store),
        "budget": Budget(episode_llm_calls=2, max_tool_calls=3, max_output_tokens=512),
        "round_index": 1,
        "llm_call_limit": 2,
        "tool_call_limit": 3,
    }
    values.update(overrides)
    return ProducerInput(**values)


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


@pytest.mark.asyncio
async def test_producer_uses_real_runner_submits_once_and_stops_after_terminal_submit(
    tmp_path: Path,
):
    store = ArtifactStore(tmp_path)
    producer_input = _producer_input(store)
    model = ScriptedLlm(
        model="scripted",
        responses=[
            tool_response("submit", _submit_args()),
            text_response("this must never receive a second request"),
        ],
    )

    output = await run_producer(producer_input, ModelSettings(), store, model)

    assert output.submission is not None
    assert output.feedback is None
    assert output.usage.llm_calls == output.usage.tool_calls == 1
    assert len(model.requests) == 1
    assert model.requests[0].config.max_output_tokens == 512


@pytest.mark.asyncio
async def test_duplicate_submit_batch_and_late_sibling_tool_are_not_charged_after_terminal_submit(
    tmp_path: Path,
):
    store = ArtifactStore(tmp_path)
    producer_input = _producer_input(store)
    model = ScriptedLlm(
        model="scripted",
        responses=[
            tool_batch_response(
                [
                    ("submit", _submit_args()),
                    ("submit", _submit_args()),
                    ("list_files", {}),
                ]
            )
        ],
    )

    output = await run_producer(producer_input, ModelSettings(), store, model)

    assert output.submission is not None
    assert output.feedback is None
    assert output.usage.tool_calls == 1
    assert len(model.requests) == 1


@pytest.mark.asyncio
async def test_tool_cap_is_charged_before_work_and_source_path_escape_is_rejected(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    producer_input = _producer_input(store, tool_call_limit=1)
    tools = build_producer_tools(producer_input, store, tool_call_limit=1)

    escaped = await tools.read_file("../private.txt", None)
    exhausted = await tools.list_files(None)

    assert "error" in escaped
    assert "normalized relative" in escaped["error"]
    assert exhausted == {"error": "tool-call budget exhausted"}
    assert tools.tool_calls == 1


def test_factories_match_agent_metadata_and_submit_has_strict_native_schema(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    tools = build_producer_tools(_producer_input(store), store)
    producer = build_producer("gemini-2.5-flash", tools=tools.native_tools())
    auditor = build_auditor("gemini-2.5-flash")
    declaration = FunctionTool(tools.submit)._get_declaration()

    assert producer.name == "producer"
    assert [tool.__name__ for tool in producer.tools] == ["read_file", "list_files", "submit"]
    assert auditor.tools == []
    assert auditor.include_contents == "none"
    assert auditor.output_schema.__name__ == "AuditResult"
    schema = declaration.parameters_json_schema
    assert set(schema["required"]) == {"control_payload", "exploit_payload", "hypothesis", "plan"}
    assert "tool_context" not in schema["properties"]
    assert schema["$defs"]["PlanRevision"]["additionalProperties"] is False
    with pytest.raises(ValueError, match="exactly match"):
        build_producer("gemini-2.5-flash", tools.native_tools()[:-1])


@pytest.mark.asyncio
async def test_invalid_plan_parent_is_typed_producer_data_not_a_provider_retry(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    producer_input = _producer_input(store)
    model = ScriptedLlm(
        model="scripted",
        responses=[tool_response("submit", _submit_args(revision=2, parent_revision=1))],
    )

    output = await run_producer(producer_input, ModelSettings(), store, model)

    assert output.submission is None
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
