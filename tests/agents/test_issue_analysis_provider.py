"""Offline SDK transport and finite semantic rubric checks, never live inference."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import httpx2
import pytest
from pydantic import ValidationError
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.usage import UsageLimits

from corsair.agents.issue_analysis import FixtureDependencies, IssueAnalysis, IssueAnalysisInput, create_issue_analysis_agent, fixture_prompt
from corsair.agents.issue_analysis.provider import LocalModelConfig, local_model
from corsair.agents.issue_analysis.skills import SKILL_ID, SKILL_SHA256, SKILL_TEXT
from evals.issue_analysis.live import HypothesisSemantics, NoUnknownToolAttempts, ProviderUsageCoverage

ROOT = Path(__file__).resolve().parents[2] / "evals/issue_analysis"


def case(name="path_traversal"):
    inputs = IssueAnalysisInput.model_validate_json((ROOT / "fixtures" / f"{name}.json").read_text())
    output = IssueAnalysis.model_validate(json.loads((ROOT / "oracles.json").read_text())["cases"][name])
    return inputs, output


@pytest.mark.parametrize("base_url", ["http://llm.example/v1", "https://llm.example", "https://key@llm.example/v1", "https://llm.example/v1?key=secret", "https://llm.example/v1#secret"])
def test_local_provider_requires_explicit_verified_endpoint(base_url):
    with pytest.raises(ValidationError):
        LocalModelConfig(server="vllm", base_url=base_url, model_name="explicit-model")


@pytest.mark.parametrize("server", [{}, {"server": "openai"}, {"server": None}])
def test_local_provider_requires_explicit_admitted_server(server):
    with pytest.raises(ValidationError):
        LocalModelConfig(base_url="https://llm.example/v1", model_name="explicit-model", **server)


@pytest.mark.parametrize("thinking_mode,thinking_token_budget,response_token_limit", [("server_default", None, 2048), ("disabled", None, 2048), ("server_default", 768, 2048), ("server_default", None, 4096), ("server_default", None, 8192), ("server_default", 2048, 16384)])
def test_native_provider_uses_explicit_model_endpoint_and_closes_client(monkeypatch, thinking_mode, thinking_token_budget, response_token_limit):
    inputs, output = case()
    requests = []
    monkeypatch.setenv("OPENAI_API_KEY", "unrelated-cloud-secret")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://unrelated.invalid/v1")
    async def respond(request):
        body = json.loads(request.content)
        requests.append(request)
        assert request.url.host == "llm.example"
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer corsair-local-anonymous"
        assert body["model"] == "explicit-model"
        if thinking_mode == "disabled":
            assert body["chat_template_kwargs"] == {"enable_thinking": False}
        else:
            assert "chat_template_kwargs" not in body
        if thinking_token_budget is None:
            assert "thinking_token_budget" not in body
        else:
            assert body["thinking_token_budget"] == thinking_token_budget
        assert "reasoning_effort" not in body
        # Model-level settings reach every request without per-run settings; the
        # native SDK sends the max_tokens setting as max_completion_tokens.
        assert (body["temperature"], body["max_completion_tokens"], body["parallel_tool_calls"]) == (0, response_token_limit, False)
        assert "response_format" not in body
        assert "strict" not in body["tools"][0]["function"]
        assert any('"hypothesis"' in str(message["content"]) for message in body["messages"])
        description = IssueAnalysis.model_json_schema()["properties"]["missing_facts"]["description"]
        assert any(description in str(message["content"]) for message in body["messages"])
        assert any(SKILL_TEXT in str(message["content"]) for message in body["messages"])
        system = body["messages"][0]["content"]
        assert '"start_line"' in system and '"end_line"' in system
        assert '"quote"' not in system and '"draft"' not in system
        assert [tool["function"]["name"] for tool in body["tools"]] == ["read_source"]
        assert body["messages"][0]["role"] == "system"
        assert sum(message["role"] == "system" for message in body["messages"]) == 1
        if len(requests) == 1:
            call = {"name": "read_source", "arguments": json.dumps({"path": "documents.py", "start_line": 1, "end_line": 4})}
            message = {"role": "assistant", "content": None, "tool_calls": [{"id": f"call-{len(requests)}", "type": "function", "function": call}]}
            finish_reason = "tool_calls"
        else:
            assert not any('"$defs"' in str(message["content"]) for message in body["messages"])
            assert [tool["function"]["name"] for tool in body["tools"]] == ["read_source"]
            tool_result = json.loads(next(item["content"] for item in body["messages"] if item["role"] == "tool"))
            assert "quote" not in tool_result
            assert [line["number"] for line in tool_result["lines"]] == [1, 2, 3, 4]
            assert "\n".join(line["text"] for line in tool_result["lines"]) == inputs.source_files[0].content.rstrip("\n")
            message = {"role": "assistant", "content": output.model_dump_json(exclude={"citations": {"__all__": {"quote"}}})}
            finish_reason = "stop"
        return httpx2.Response(200, json={"id": f"fixture-{len(requests)}", "object": "chat.completion", "created": 1,
                                        "model": "explicit-model", "choices": [{"index": 0, "finish_reason": finish_reason, "message": message}],
                                        "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}})
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(respond))
    async def exercise():
        async with local_model(LocalModelConfig(server="vllm", base_url="https://llm.example/v1", model_name="explicit-model",
                                                response_token_limit=response_token_limit, thinking_mode=thinking_mode,
                                                thinking_token_budget=thinking_token_budget), http_client=client) as model:
            assert model.provider.client.max_retries == 0
            assert (model.system, model.provider.name) == ("vllm", "vllm")
            result = await create_issue_analysis_agent(model).run(fixture_prompt(inputs), deps=FixtureDependencies(inputs),
                                                                usage_limits=UsageLimits(request_limit=3, tool_calls_limit=1))
            assert result.output == output
            assert all(message.provider_name == "vllm" for message in result.all_messages() if isinstance(message, ModelResponse))
            assert result.usage.input_tokens == 40 and result.usage.output_tokens == 20
            assert result.usage.requests == 2 and result.usage.tool_calls == 1
            assert all(message.provider_response_id for message in result.all_messages() if isinstance(message, ModelResponse))
    asyncio.run(exercise())
    assert len(requests) == 2 and client.is_closed


@pytest.mark.parametrize("options", [{"thinking_token_budget": 0}, {"thinking_token_budget": 2049},
                                    {"thinking_token_budget": True},
                                    {"thinking_mode": "disabled", "thinking_token_budget": 768},
                                    {"response_token_limit": 3000}, {"response_token_limit": 32768},
                                    {"timeout_seconds": 241}])
def test_provider_refuses_invalid_or_conflicting_thinking_budget(options):
    with pytest.raises(ValidationError):
        LocalModelConfig(server="vllm", base_url="https://llm.example/v1", model_name="explicit-model", **options)


@pytest.mark.parametrize("status", [401, 429, 500])
def test_native_provider_error_is_preserved_without_hidden_retry(status):
    requests = []
    async def respond(request):
        requests.append(request)
        return httpx2.Response(status, json={"error": {"message": "synthetic transport failure", "type": "provider_fixture"}})
    async def exercise():
        client = httpx2.AsyncClient(transport=httpx2.MockTransport(respond))
        async with local_model(LocalModelConfig(server="vllm", base_url="https://llm.example/v1", model_name="explicit-model"), http_client=client) as model:
            inputs, _ = case()
            with pytest.raises(ModelHTTPError) as error:
                await create_issue_analysis_agent(model).run(fixture_prompt(inputs), deps=FixtureDependencies(inputs))
            assert error.value.status_code == status
    asyncio.run(exercise())
    assert len(requests) == 1


def test_explicit_local_credential_configuration_refuses_missing_key(monkeypatch):
    monkeypatch.delenv("CORSAIR_LOCAL_MODEL_API_KEY", raising=False)
    async def exercise():
        with pytest.raises(ValueError, match="credential is unavailable"):
            async with local_model(LocalModelConfig(server="vllm", base_url="https://llm.example/v1", model_name="explicit-model", api_key_env="CORSAIR_LOCAL_MODEL_API_KEY")):
                pytest.fail("missing explicit credential must refuse construction")
    asyncio.run(exercise())


@pytest.mark.parametrize("field,value", [("entry_point", "wrong_function"), ("attacker_input", "unrelated_parameter"), ("sensitive_operation", "print"), ("observable_effect", "success"), ("attacker_capabilities", "read host credentials")])
def test_finite_semantic_rubric_rejects_wrong_component_facts(field, value):
    inputs, output = case()
    hypothesis = output.hypothesis.model_copy(update={field: value})
    changed = output.model_copy(update={"hypothesis": hypothesis})
    assert not HypothesisSemantics().evaluate(SimpleNamespace(inputs=inputs, output=changed)).value


def test_semantic_rubric_accepts_paraphrase_and_missing_information():
    inputs, output = case()
    changed = output.model_copy(update={"hypothesis": output.hypothesis.model_copy(update={"observable_effect": "An existing readable file outside root may be disclosed."})})
    assert HypothesisSemantics().evaluate(SimpleNamespace(inputs=inputs, output=changed)).value
    inputs, output = case("missing_source")
    assert HypothesisSemantics().evaluate(SimpleNamespace(inputs=inputs, output=output)).value


def test_saved_path_output_paraphrase_and_split_citations_keep_precondition_failure():
    inputs, output = case()
    # Reviewed live008 path repeat 2 facts, copied without reading private
    # evidence at test time. Correcting rubric admission must not make it pass.
    deps = FixtureDependencies(inputs)
    changed = output.model_copy(update={
        "citations": (deps.read_source("documents.py", 3, 3), deps.read_source("documents.py", 4, 4)),
        "hypothesis": output.hypothesis.model_copy(update={
            "sensitive_operation": "Path construction and file reading",
            "preconditions": ("root is a valid Path object",),
        }),
    })
    verdict = HypothesisSemantics().evaluate(SimpleNamespace(inputs=inputs, output=changed))
    assert not verdict.value and verdict.reason == "failed finite predicates: preconditions"
    corrected = changed.model_copy(update={"hypothesis": changed.hypothesis.model_copy(update={
        "preconditions": ("The target file exists.", "The process has read permission for it."),
    })})
    assert HypothesisSemantics().evaluate(SimpleNamespace(inputs=inputs, output=corrected)).value


@pytest.mark.parametrize("preconditions", [
    ("The caller supplies filename without prior confinement.",),
    ("The file exists.",),
    ("The process has read permission.",),
    ("The file need not exist; no read permission is necessary.",),
])
def test_semantic_rubric_requires_target_existence_and_read_permission(preconditions):
    inputs, output = case()
    changed = output.model_copy(update={"hypothesis": output.hypothesis.model_copy(update={"preconditions": preconditions})})
    assert not HypothesisSemantics().evaluate(SimpleNamespace(inputs=inputs, output=changed)).value


@pytest.mark.parametrize("operation", ["Path construction only", "File writing", "No file reading occurs", "Does not read file contents"])
def test_semantic_rubric_rejects_opposite_file_operation(operation):
    inputs, output = case()
    changed = output.model_copy(update={"hypothesis": output.hypothesis.model_copy(update={"sensitive_operation": operation})})
    assert not HypothesisSemantics().evaluate(SimpleNamespace(inputs=inputs, output=changed)).value


@pytest.mark.parametrize("line", [3, 4])
def test_semantic_rubric_rejects_incomplete_combined_citations(line):
    inputs, output = case()
    changed = output.model_copy(update={"citations": (FixtureDependencies(inputs).read_source("documents.py", line, line),)})
    assert not HypothesisSemantics().evaluate(SimpleNamespace(inputs=inputs, output=changed)).value


def test_fixture_prompt_exposes_exact_read_bounds_without_source_or_oracle():
    inputs, output = case()
    prompt = fixture_prompt(inputs)
    assert "documents.py (saved-file inclusive lines 1..4)" in prompt
    assert inputs.source_files[0].content not in prompt
    assert inputs.fixture_id not in prompt
    assert output.hypothesis.observable_effect not in prompt


def test_guarded_source_contrast_refuses_unguarded_hypothesis():
    _, output = case()
    inputs = IssueAnalysisInput.model_validate_json((ROOT / "fixtures/confined_source.json").read_text())
    assert not HypothesisSemantics().evaluate(SimpleNamespace(inputs=inputs, output=output)).value


@pytest.mark.parametrize("effect", [
    "The confinement guard fails and the attacker reads files outside the allowed root.",
    "ValueError is raised, but the attacker reads files outside the allowed root.",
    "The guard rejects traversal but discloses an arbitrary file outside the root.",
])
def test_guarded_source_contrast_refuses_opposite_disclosure_claim(effect):
    _, output = case()
    inputs = IssueAnalysisInput.model_validate_json((ROOT / "fixtures/confined_source.json").read_text())
    citation = FixtureDependencies(inputs).read_source("documents.py", 6, 6)
    changed = output.model_copy(update={"citations": (citation,), "hypothesis": output.hypothesis.model_copy(update={"observable_effect": effect})})
    assert not HypothesisSemantics().evaluate(SimpleNamespace(inputs=inputs, output=changed)).value


def test_guarded_source_contrast_accepts_rejection_before_read():
    _, output = case()
    inputs = IssueAnalysisInput.model_validate_json((ROOT / "fixtures/confined_source.json").read_text())
    citation = FixtureDependencies(inputs).read_source("documents.py", 6, 6)
    changed = output.model_copy(update={"citations": (citation,), "hypothesis": output.hypothesis.model_copy(update={"observable_effect": "relative_to raises ValueError before read_text; the outside file is not read."})})
    assert HypothesisSemantics().evaluate(SimpleNamespace(inputs=inputs, output=changed)).value


def test_provider_usage_coverage_refuses_missing_measurements():
    assert not ProviderUsageCoverage().evaluate(SimpleNamespace(attributes={})).value
    assert not ProviderUsageCoverage().evaluate(SimpleNamespace(attributes={"provider_usage_present": False})).value
    assert ProviderUsageCoverage().evaluate(SimpleNamespace(attributes={"provider_usage_present": True})).value


def test_no_unknown_tool_attempts_fails_closed():
    assert not NoUnknownToolAttempts().evaluate(SimpleNamespace(attributes={})).value
    assert not NoUnknownToolAttempts().evaluate(SimpleNamespace(attributes={"unknown_tool_attempts": 1})).value
    assert NoUnknownToolAttempts().evaluate(SimpleNamespace(attributes={"unknown_tool_attempts": 0})).value


@pytest.mark.parametrize("extra,expected", [([], (2048, 60)), (["--response-token-limit", "16384", "--timeout-seconds", "180"], (16384, 180))])
def test_live_cli_passes_response_cap_and_timeout(monkeypatch, tmp_path, extra, expected):
    from evals.issue_analysis import live
    seen = []
    async def capture(config, evidence, **options):
        seen.append((config.response_token_limit, config.timeout_seconds))
        raise SystemExit(0)
    monkeypatch.setattr(live, "evaluate_local", capture)
    monkeypatch.setattr("sys.argv", ["live", "--base-url", "https://llm.example/v1", "--model", "explicit-model",
                                     "--evidence", str(tmp_path / "run"), *extra])
    with pytest.raises(SystemExit):
        live.main()
    assert seen == [expected]


@pytest.mark.parametrize("first_tool", ["read_source", "run_shell"])
def test_live_evaluation_records_config_counts_and_run_identity_offline(monkeypatch, tmp_path, first_tool):
    from evals.issue_analysis import live
    _, output = case()
    requests = []
    async def respond(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            call = {"name": first_tool, "arguments": json.dumps({"path": "documents.py", "start_line": 1, "end_line": 4})}
            message = {"role": "assistant", "content": None, "tool_calls": [{"id": "call-1", "type": "function", "function": call}]}
        else:
            message = {"role": "assistant", "content": output.model_dump_json(exclude={"citations": {"__all__": {"quote"}}})}
        return httpx2.Response(200, json={"id": f"fixture-{len(requests)}", "object": "chat.completion", "created": 1,
                                        "model": "explicit-model", "choices": [{"index": 0, "finish_reason": "stop", "message": message}],
                                        "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}})
    offline = local_model
    monkeypatch.setattr(live, "local_model", lambda config: offline(
        config, http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(respond))))
    config = LocalModelConfig(server="vllm", base_url="https://llm.example/v1", model_name="explicit-model",
                              thinking_mode="disabled")
    report = asyncio.run(live.evaluate_local(config, tmp_path, repeat=1, case_names=("path_traversal",)))
    metadata = report.experiment_metadata
    assert metadata["server"] == "vllm" and metadata["model"]["system"] == "vllm"
    assert metadata["model"]["model_settings"] == {"temperature": 0, "max_tokens": 2048, "parallel_tool_calls": False,
                                                   "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
    assert (metadata["thinking_mode"], metadata["thinking_token_budget"]) == ("disabled", None)
    assert (metadata["skill_id"], metadata["skill_sha256"]) == (SKILL_ID, SKILL_SHA256)
    assert (metadata["model_output_contract"], metadata["final_output_contract"]) == ("IssueAnalysisDraft", "IssueAnalysis")
    assert all(request["chat_template_kwargs"] == {"enable_thinking": False} for request in requests)
    assert metadata["model"]["sdk_max_retries"] == 0
    assert metadata["model"]["profile"]["json_schema_transformer"] == "InlineDefsJsonSchemaTransformer"
    assert metadata["model"]["profile"]["openai_chat_supports_multiple_system_messages"] is False
    assert (metadata["tool_retries"], metadata["output_retries"]) == (0, 1)
    receipt = json.loads(next(tmp_path.glob("path-traversal-component-v1-*.json")).read_text())
    assert receipt["run_id"] and receipt["config_version"] == metadata["config_version"]
    assert {message["run_id"] for message in receipt["messages"]} == {receipt["run_id"]}
    if first_tool == "read_source":
        assert receipt["completed"] and (receipt["unknown_tool_attempts"], receipt["output_corrections"]) == (0, 0)
        attributes = report.cases[0].attributes
        assert (attributes["unknown_tool_attempts"], attributes["output_corrections"]) == (0, 0)
        assert attributes["run_id"] == receipt["run_id"]
        assert all(report.cases[0].assertions[name].value for name in ("NoUnknownToolAttempts", "HypothesisSemantics"))
    else:
        # The invented tool is refused at once and is attributable from the retained messages.
        assert len(requests) == 1 and not report.cases and len(report.failures) == 1
        assert not receipt["completed"] and receipt["failure"]["type"] == "UnexpectedModelBehavior"
        assert receipt["unknown_tool_attempts"] == 1
