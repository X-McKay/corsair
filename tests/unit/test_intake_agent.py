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


async def test_native_completion_errors_are_categorical_not_raw_model_text(tmp_path):
    from corsair.adapters.storage.filesystem import ArtifactStore

    model = ScriptedLlm(
        model="scripted-invalid-completion",
        structured_tools=False,
        responses=[
            tool_response("set_model_response", {"scope": "in_scope"}),
            tool_response("set_model_response", proposal_dict()),
        ],
    )
    result = await run_intake(prepared(ArtifactStore(tmp_path)), Settings(), Reader(), model)
    assert result.proposal is not None
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
