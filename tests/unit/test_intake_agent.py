"""Real native ADK runner with a scripted model, not a live-quality claim."""

import json

import pytest

from corsair.adapters.inference.intake_agent import run_intake
from corsair.agents.intake.factory import build_intake
from corsair.contracts import Source
from corsair.contracts.intake_agent import (
    ImageInventory,
    IntakeProposal,
    IntakeRequest,
    JsonIssueInput,
    PreparedIntake,
)
from corsair.settings import Settings
from tests.unit.adk import ScriptedLlm, text_response, tool_response


def prepared(store):
    payload = {"title": "Traversal", "description": "Private file disclosure", "locations": []}
    artifact = store.put_json(payload)
    return PreparedIntake(
        run_id="intake-test",
        request=IntakeRequest(
            input=JsonIssueInput(payload=payload), source=Source(path="/private/host-source")
        ),
        source=artifact,
        input_artifact=artifact,
        payload=payload,
        inventory=ImageInventory(),
        config_digest="0" * 64,
    )


class Reader:
    def read(self, operation, relative=""):
        del relative
        if operation == "list":
            return {"files": ["reader.py"], "truncated": False}
        return {"content": "def read_file(path): return path"}


def proposal_dict():
    return {
        "issue": {"title": "Traversal", "description": "Private file disclosure", "locations": []},
        "scope": "in_scope",
        "surface": "function",
        "language": "python",
        "execution_mode": "callable",
        "requirements": [],
        "suggested_image": None,
        "reason_codes": ["NO_COMPATIBLE_IMAGE"],
        "locations": [{"path": "reader.py"}],
    }


def test_intake_factory_uses_canonical_schema():
    agent = build_intake("gemini-2.5-flash", Reader(), ImageInventory())
    assert agent.output_schema is IntakeProposal
    assert [getattr(tool, "__name__", None) for tool in agent.tools[:-1]] == [
        "read_file",
        "list_files",
        "compare_images",
    ]


async def test_native_intake_tools_and_structured_output(tmp_path):
    from corsair.adapters.storage.filesystem import ArtifactStore

    model = ScriptedLlm(
        model="scripted-intake",
        responses=[tool_response("list_files", {}), text_response(json.dumps(proposal_dict()))],
    )
    result = await run_intake(prepared(ArtifactStore(tmp_path)), Settings(), Reader(), model)
    assert result.error_code is None
    assert result.proposal is not None
    assert result.usage.llm_calls == 2 and result.usage.tool_calls == 1
    assert result.tool_counts == {"list_files": 1}
    assert result.source_preloaded == ["reader.py"]
    assert "/private/host-source" not in str(model.requests)


@pytest.mark.parametrize("failed_operation", ["list", "read"])
async def test_source_preload_error_is_inspection_failure_before_model_dispatch(
    tmp_path, failed_operation
):
    from corsair.adapters.storage.filesystem import ArtifactStore

    class UnavailableReader(Reader):
        def read(self, operation, relative=""):
            if operation == failed_operation:
                raise RuntimeError("PRIVATE_READER_ERROR")
            return super().read(operation, relative)

    model = ScriptedLlm(model="unused", responses=[])
    output = await run_intake(
        prepared(ArtifactStore(tmp_path)), Settings(), UnavailableReader(), model
    )
    assert output.error_code == "INSPECTION_FAILED"
    assert output.error_stage == "inspection" and output.error_type == "RuntimeError"
    assert model.requests == []
    assert "PRIVATE_READER_ERROR" not in output.model_dump_json()


async def test_native_intake_rejects_invented_image(tmp_path):
    from corsair.adapters.storage.filesystem import ArtifactStore

    value = proposal_dict()
    value["suggested_image"] = "python:imagined"
    model = ScriptedLlm(model="scripted-intake", responses=[text_response(json.dumps(value))])
    result = await run_intake(prepared(ArtifactStore(tmp_path)), Settings(), Reader(), model)
    assert result.error_code == "OUTPUT_INVALID" and result.proposal is None
    assert result.output_failure == "IMAGE_OUTSIDE_INVENTORY"


async def test_native_intake_schema_completion_tool(tmp_path):
    from corsair.adapters.storage.filesystem import ArtifactStore

    model = ScriptedLlm(
        model="scripted-intake-completion",
        structured_tools=False,
        responses=[tool_response("set_model_response", proposal_dict())],
    )
    result = await run_intake(prepared(ArtifactStore(tmp_path)), Settings(), Reader(), model)
    assert result.proposal is not None
    assert result.tool_counts == {"set_model_response": 1}


@pytest.mark.parametrize("unread_path", [False, True])
async def test_native_completion_errors_are_categorical_not_raw_model_text(tmp_path, unread_path):
    from corsair.adapters.storage.filesystem import ArtifactStore

    proposal = proposal_dict()
    if unread_path:
        proposal["locations"] = [{"path": "unread.py"}]
    model = ScriptedLlm(
        model="scripted-invalid-completion",
        structured_tools=False,
        responses=[
            tool_response("set_model_response", {"scope": "in_scope"}),
            tool_response("set_model_response", proposal),
        ],
    )
    result = await run_intake(prepared(ArtifactStore(tmp_path)), Settings(), Reader(), model)
    assert (result.proposal is not None) is (not unread_path)
    assert result.output_failure == ("SOURCE_NOT_INSPECTED" if unread_path else None)
    assert result.completion_errors["missing:issue"] == 1


async def test_native_reads_can_expand_grounded_paths(tmp_path):
    from corsair.adapters.storage.filesystem import ArtifactStore

    value = proposal_dict()
    value["locations"] = [{"path": "extra.py"}]
    model = ScriptedLlm(
        model="scripted-extra-source",
        responses=[
            tool_response("read_file", {"path": "extra.py"}),
            text_response(json.dumps(value)),
        ],
    )
    result = await run_intake(prepared(ArtifactStore(tmp_path)), Settings(), Reader(), model)
    assert result.proposal is not None


async def test_truncated_preload_is_not_source_grounding(tmp_path):
    from corsair.adapters.storage.filesystem import ArtifactStore

    class TruncatedReader(Reader):
        def read(self, operation, relative=""):
            return (
                super().read(operation, relative)
                if operation == "list"
                else {"content": "partial", "truncated": True}
            )

    model = ScriptedLlm(
        model="truncated-intake", responses=[text_response(json.dumps(proposal_dict()))]
    )
    result = await run_intake(
        prepared(ArtifactStore(tmp_path)), Settings(), TruncatedReader(), model
    )
    assert result.proposal is None and result.output_failure == "SOURCE_NOT_INSPECTED"
    assert result.source_preloaded == []


async def test_truncated_tool_read_cannot_ground_an_unread_path(tmp_path):
    from corsair.adapters.storage.filesystem import ArtifactStore

    class PartialExtra(Reader):
        def read(self, operation, relative=""):
            if operation == "read" and relative == "extra.py":
                return {"content": "partial", "truncated": True}
            return super().read(operation, relative)

    value = proposal_dict()
    value["locations"] = [{"path": "extra.py"}]
    model = ScriptedLlm(
        model="truncated-tool",
        responses=[
            tool_response("read_file", {"path": "extra.py"}),
            text_response(json.dumps(value)),
        ],
    )
    result = await run_intake(prepared(ArtifactStore(tmp_path)), Settings(), PartialExtra(), model)
    assert result.proposal is None and result.output_failure == "SOURCE_NOT_INSPECTED"


async def test_schema_failure_records_categories_without_response_contents(tmp_path):
    from corsair.adapters.storage.filesystem import ArtifactStore

    value = proposal_dict()
    value["issue"] = "private-response-value"
    model = ScriptedLlm(model="invalid-intake-json", responses=[text_response(json.dumps(value))])
    result = await run_intake(prepared(ArtifactStore(tmp_path)), Settings(), Reader(), model)
    assert result.error_code == "OUTPUT_INVALID"
    assert result.completion_errors.get("schema:model_type") == 1
    assert "private-response-value" not in result.model_dump_json()


def test_native_intake_requests_json_completion():
    agent = build_intake("gemini-2.5-flash", Reader(), ImageInventory())
    assert agent.generate_content_config is not None
    assert agent.generate_content_config.response_mime_type == "application/json"


async def test_canonical_issue_packet_is_single_and_preload_is_explicit(tmp_path):
    from corsair.adapters.storage.filesystem import ArtifactStore

    model = ScriptedLlm(
        model="single-issue", responses=[text_response(json.dumps(proposal_dict()))]
    )
    item = prepared(ArtifactStore(tmp_path))
    await run_intake(item, Settings(), Reader(), model)
    message = next(content for content in model.requests[0].contents if content.role == "user")
    assert message.parts and isinstance(message.parts[0].text, str)
    packet = json.loads(message.parts[0].text)
    assert packet["canonical_issue"] == item.payload
    assert packet["issue_input"] is None
    assert packet["inspected_paths"] == ["reader.py"]
    assert packet["source_context"][0]["content"] == "def read_file(path): return path"
    assert model.requests[0].config.response_schema is IntakeProposal


@pytest.mark.parametrize(
    "payload",
    [
        [{"finding": {"message": "Traversal in reader.py"}}],
        {"results": [{"extra": {"message": "Traversal"}, "path": "reader.py"}]},
        '{"finding":{"message":"Traversal in reader.py"}}',
        {"finding": "Traversal", "source": "/etc/private", "image": "unavailable:latest"},
    ],
)
async def test_noncanonical_json_reaches_native_agent_as_data(tmp_path, payload):
    from corsair.adapters.storage.filesystem import ArtifactStore

    item = prepared(ArtifactStore(tmp_path))
    item = item.model_copy(
        update={
            "payload": payload,
            "request": item.request.model_copy(update={"input": JsonIssueInput(payload=payload)}),
        }
    )
    model = ScriptedLlm(
        model="raw-scanner-data", responses=[text_response(json.dumps(proposal_dict()))]
    )
    output = await run_intake(item, Settings(), Reader(), model)
    assert output.proposal is not None
    message = next(content for content in model.requests[0].contents if content.role == "user")
    assert message.parts and isinstance(message.parts[0].text, str)
    packet = json.loads(message.parts[0].text)
    assert packet["canonical_issue"] is None
    assert packet["issue_input"] == payload
    assert packet["available_images"] == []
    assert "/private/host-source" not in message.parts[0].text


@pytest.mark.parametrize("structured_tools", [True, False])
@pytest.mark.parametrize("has_image", [True, False])
async def test_native_image_comparison_and_skill_load_are_real_accounted_calls(
    tmp_path, structured_tools, has_image
):
    from corsair.adapters.storage.filesystem import ArtifactStore
    from tests.unit.test_agents_runtime import _tool_response
    from tests.unit.test_intake_images import inventory

    item = prepared(ArtifactStore(tmp_path))
    value = proposal_dict()
    if has_image:
        item = item.model_copy(update={"inventory": inventory()})
        value.update(suggested_image="python-local:callable", reason_codes=[])

    model = ScriptedLlm(
        model="image-procedure",
        structured_tools=structured_tools,
        responses=[
            tool_response("load_skill", {"skill_name": "image-selection"}),
            tool_response(
                "compare_images",
                {"language": "python", "execution_mode": "callable", "requirements": []},
            ),
            text_response(json.dumps(value))
            if structured_tools
            else tool_response("set_model_response", value),
        ],
    )
    output = await run_intake(item, Settings(), Reader(), model)
    assert output.proposal is not None
    assert output.usage.llm_calls == 3 and output.usage.tool_calls == 2 + int(not structured_tools)
    assert output.usage.skills_preloaded == ["image-selection"]
    assert output.usage.skills_loaded == ["image-selection"]
    assert output.tool_counts == {
        "compare_images": 1,
        **({} if structured_tools else {"set_model_response": 1}),
    }
    candidates = _tool_response(model, "compare_images")["images"]
    if has_image:
        assert candidates[0]["compatible"] is True
        assert output.proposal.suggested_image == candidates[0]["reference"]
        from corsair.policies.intake_agent import classify_intake

        assert (
            classify_intake(output.proposal, item.inventory).classification == "in_scope_supported"
        )
    else:
        assert candidates == [] and output.proposal.suggested_image is None
    assert {"compare_images", "load_skill", "load_skill_resource"} <= set(
        model.requests[0].tools_dict
    )


async def test_intake_native_skill_refresh_limit_remains_enforced(tmp_path):
    from corsair.adapters.storage.filesystem import ArtifactStore

    model = ScriptedLlm(
        model="image-skill-limit",
        responses=[
            tool_response("load_skill", {"skill_name": "image-selection"}),
            tool_response("load_skill", {"skill_name": "image-selection"}),
            text_response(json.dumps(proposal_dict())),
        ],
    )
    output = await run_intake(prepared(ArtifactStore(tmp_path)), Settings(), Reader(), model)
    assert output.proposal is None
    assert output.output_failure == "TOOL_BUDGET_EXHAUSTED"
    assert output.usage.skills_loaded == ["image-selection"]
    assert output.usage.tool_calls == 1


async def test_intake_refuses_main_unsupported_tool_schema_route_before_dispatch(tmp_path):
    from corsair.adapters.storage.filesystem import ArtifactStore

    class NoInspection:
        def read(self, operation: str, relative: str = "") -> dict:
            del operation, relative
            raise AssertionError("unsupported route must stop before inspection or model dispatch")

    settings = Settings(
        models={
            "connector": "litellm",
            "producer": "gemini/gemini-2.5-flash",
            "intake": "openai/local-vllm",
            "api_base": "https://llm.almckay.io/v1",
        }
    )
    output = await run_intake(prepared(ArtifactStore(tmp_path)), settings, NoInspection())
    assert output.error_code == "MODEL_CONFIGURATION_UNSUPPORTED"
    assert output.usage.llm_calls == 0 and output.inspection_reads == 0


async def test_preload_time_is_deducted_before_model_dispatch(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from corsair.adapters.inference import intake_agent
    from corsair.adapters.storage.filesystem import ArtifactStore

    clock = iter([0.0, 2.0, 2.0])
    monkeypatch.setattr(intake_agent, "time", SimpleNamespace(perf_counter=lambda: next(clock)))
    model = ScriptedLlm(
        model="expired-preload", responses=[text_response(json.dumps(proposal_dict()))]
    )
    item = prepared(ArtifactStore(tmp_path)).model_copy(update={"episode_seconds": 1})
    output = await run_intake(item, Settings(), Reader(), model)
    assert output.error_code == "MODEL_FAILED" and not model.requests
    assert output.inspection_reads == 2 and output.usage.seconds == 2.0


async def test_activity_deducts_sandbox_setup_time(tmp_path, monkeypatch):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.contracts.intake_agent import IntakeAgentOutput
    from corsair.steps import intake_agent

    @asynccontextmanager
    async def client_session():
        yield object()

    @asynccontextmanager
    async def inspection_session(inspection):
        yield inspection

    seen = []

    async def run(bounded, settings, reader):
        del settings, reader
        seen.append(bounded.episode_seconds)
        return IntakeAgentOutput(error_code="MODEL_FAILED")

    clock = iter([0.0, 3.1])
    monkeypatch.setattr(intake_agent, "time", SimpleNamespace(perf_counter=lambda: next(clock)))
    monkeypatch.setattr("corsair.adapters.sandboxing.images.docker_client", client_session)
    monkeypatch.setattr(intake_agent, "inspection_session", inspection_session)
    monkeypatch.setattr(
        intake_agent, "DockerInspection", lambda *args: SimpleNamespace(image_id=None)
    )
    monkeypatch.setattr(intake_agent, "run_intake", run)
    monkeypatch.setattr(intake_agent.activity, "heartbeat", lambda *args: None)
    settings = Settings()
    store = ArtifactStore(tmp_path)
    item = prepared(store).model_copy(
        update={"episode_seconds": 10, "config_digest": settings.identity}
    )
    result = await intake_agent.IntakeActivities(settings, store).analyze(item)
    assert seen == [6]
    assert result.decision.error_code == "MODEL_FAILED"


@pytest.mark.parametrize("failure", ["schema", "inspection"])
async def test_activity_records_categorical_diagnostics_without_exception_content(
    tmp_path, monkeypatch, caplog, failure
):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.contracts.intake_agent import IntakeAgentOutput, IntakeResult
    from corsair.steps import intake_agent

    @asynccontextmanager
    async def client_session():
        yield object()

    @asynccontextmanager
    async def inspection_session(inspection):
        if failure == "inspection":
            raise RuntimeError("PRIVATE_PROVIDER_BODY")
        yield inspection

    async def run(*args):
        del args
        return IntakeAgentOutput(
            error_code="OUTPUT_INVALID",
            output_failure="SCHEMA_INVALID",
            completion_errors={"schema:missing": 1},
            tool_counts={"list_files": 1},
        )

    monkeypatch.setattr("corsair.adapters.sandboxing.images.docker_client", client_session)
    monkeypatch.setattr(intake_agent, "inspection_session", inspection_session)
    monkeypatch.setattr(
        intake_agent, "DockerInspection", lambda *args: SimpleNamespace(image_id=None)
    )
    monkeypatch.setattr(intake_agent, "run_intake", run)
    monkeypatch.setattr(intake_agent.activity, "heartbeat", lambda *args: None)
    caplog.set_level("INFO", logger="corsair")
    settings = Settings()
    store = ArtifactStore(tmp_path)
    activities = intake_agent.IntakeActivities(settings, store)
    item = prepared(store).model_copy(update={"config_digest": settings.identity})
    result = await activities.record(await activities.analyze(item))
    assert result.result_artifact is not None
    saved = IntakeResult.model_validate(store.get_json(result.result_artifact))
    if failure == "schema":
        assert saved.diagnostics.output_failure == "SCHEMA_INVALID"
        assert saved.diagnostics.completion_errors == {"schema:missing": 1}
        assert saved.diagnostics.tool_counts == {"list_files": 1}
    else:
        assert saved.diagnostics.error_stage == "inspection"
        assert saved.diagnostics.error_type == "RuntimeError"
    logs = [getattr(record, "fields", {}) for record in caplog.records]
    assert any(
        item.get("run_id") == "intake-test" and item.get("error_code") == saved.decision.error_code
        for item in logs
    )
    assert "PRIVATE_PROVIDER_BODY" not in saved.model_dump_json() + str(logs)


@pytest.mark.parametrize("hosted_vllm", [False, True])
async def test_native_completion_exposes_explicit_nested_object_type(tmp_path, hosted_vllm):
    """vLLM's parser needs the object type beside the Pydantic reference."""
    from corsair.adapters.storage.filesystem import ArtifactStore

    model = ScriptedLlm(
        model="nested-object-schema",
        structured_tools=False,
        responses=[tool_response("set_model_response", proposal_dict())],
    )
    settings = (
        Settings(models={"connector": "litellm", "intake": "hosted_vllm/qwen"})
        if hosted_vllm
        else Settings()
    )
    result = await run_intake(prepared(ArtifactStore(tmp_path)), settings, Reader(), model)
    assert result.proposal is not None
    assert model.requests[0].config is not None
    declarations = [
        declaration
        for tool in model.requests[0].config.tools or []
        for declaration in tool.function_declarations or []
        if declaration.name == "set_model_response"
    ]
    assert len(declarations) == 1
    schema = declarations[0].parameters_json_schema
    assert isinstance(schema, dict)
    assert schema["properties"]["issue"].get("type") == ("object" if hosted_vllm else None)
    assert schema["properties"]["issue"]["$ref"] == "#/$defs/Issue"
    assert schema["$defs"]["Issue"]["additionalProperties"] is False
    assert result.usage.llm_calls == result.usage.tool_calls == 1
    assert "type" not in IntakeProposal.model_json_schema()["properties"]["issue"]


def test_explicit_object_schema_still_rejects_json_encoded_issue():
    from pydantic import ValidationError

    value = proposal_dict()
    value["issue"] = json.dumps(value["issue"])
    with pytest.raises(ValidationError):
        IntakeProposal.model_validate(value)


async def test_hosted_vllm_schema_callback_preserves_native_call_limit(tmp_path):
    from corsair.adapters.storage.filesystem import ArtifactStore

    item = prepared(ArtifactStore(tmp_path))
    item = item.model_copy(
        update={
            "request": item.request.model_copy(
                update={
                    "budget": item.request.budget.model_copy(
                        update={"max_llm_calls": 1, "episode_llm_calls": 1}
                    )
                }
            )
        }
    )
    settings = Settings(models={"connector": "litellm", "intake": "hosted_vllm/qwen"})
    model = ScriptedLlm(
        model="limited-qwen",
        structured_tools=False,
        responses=[
            tool_response("list_files", {}),
            tool_response("set_model_response", proposal_dict()),
        ],
    )
    output = await run_intake(item, settings, Reader(), model)
    assert output.output_failure == "LLM_BUDGET_EXHAUSTED"
    assert output.usage.llm_calls == len(model.requests) == 1
    assert output.proposal is None
