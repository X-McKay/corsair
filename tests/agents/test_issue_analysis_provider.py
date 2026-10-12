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
from evals.issue_analysis.live import HypothesisSemantics, ProviderUsageCoverage

ROOT = Path(__file__).resolve().parents[2] / "evals/issue_analysis"


def case(name="path_traversal"):
    inputs = IssueAnalysisInput.model_validate_json((ROOT / "fixtures" / f"{name}.json").read_text())
    output = IssueAnalysis.model_validate(json.loads((ROOT / "oracles.json").read_text())["cases"][name])
    return inputs, output


@pytest.mark.parametrize("base_url", ["http://llm.example/v1", "https://llm.example", "https://key@llm.example/v1", "https://llm.example/v1?key=secret", "https://llm.example/v1#secret"])
def test_local_provider_requires_explicit_verified_endpoint(base_url):
    with pytest.raises(ValidationError):
        LocalModelConfig(base_url=base_url, model_name="explicit-model")


def test_native_provider_uses_explicit_model_endpoint_and_closes_client(monkeypatch):
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
        assert "response_format" not in body
        assert "strict" not in body["tools"][0]["function"]
        assert any('"hypothesis"' in str(message["content"]) for message in body["messages"])
        assert body["messages"][0]["role"] == "system"
        assert sum(message["role"] == "system" for message in body["messages"]) == 1
        if len(requests) == 1:
            call = {"name": "read_source", "arguments": json.dumps({"path": "documents.py", "start_line": 1, "end_line": 4})}
            message = {"role": "assistant", "content": None, "tool_calls": [{"id": f"call-{len(requests)}", "type": "function", "function": call}]}
            finish_reason = "tool_calls"
        else:
            assert not any('"$defs"' in str(message["content"]) for message in body["messages"])
            assert [tool["function"]["name"] for tool in body["tools"]] == ["read_source"]
            message = {"role": "assistant", "content": output.model_dump_json()}
            finish_reason = "stop"
        return httpx2.Response(200, json={"id": f"fixture-{len(requests)}", "object": "chat.completion", "created": 1,
                                        "model": "explicit-model", "choices": [{"index": 0, "finish_reason": finish_reason, "message": message}],
                                        "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}})
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(respond))
    async def exercise():
        async with local_model(LocalModelConfig(base_url="https://llm.example/v1", model_name="explicit-model"), http_client=client) as model:
            assert model.provider.client.max_retries == 0
            result = await create_issue_analysis_agent(model).run(fixture_prompt(inputs), deps=FixtureDependencies(inputs),
                                                                usage_limits=UsageLimits(request_limit=3, tool_calls_limit=1))
            assert result.output == output
            assert result.usage.input_tokens == 40 and result.usage.output_tokens == 20
            assert result.usage.requests == 2 and result.usage.tool_calls == 1
            assert all(message.provider_response_id for message in result.all_messages() if isinstance(message, ModelResponse))
    asyncio.run(exercise())
    assert len(requests) == 2 and client.is_closed


@pytest.mark.parametrize("status", [401, 429, 500])
def test_native_provider_error_is_preserved_without_hidden_retry(status):
    requests = []
    async def respond(request):
        requests.append(request)
        return httpx2.Response(status, json={"error": {"message": "synthetic transport failure", "type": "provider_fixture"}})
    async def exercise():
        client = httpx2.AsyncClient(transport=httpx2.MockTransport(respond))
        async with local_model(LocalModelConfig(base_url="https://llm.example/v1", model_name="explicit-model"), http_client=client) as model:
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
            async with local_model(LocalModelConfig(base_url="https://llm.example/v1", model_name="explicit-model", api_key_env="CORSAIR_LOCAL_MODEL_API_KEY")):
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


def test_fixture_prompt_exposes_exact_read_bounds_without_source_or_oracle():
    inputs, output = case()
    prompt = fixture_prompt(inputs)
    assert "documents.py (inclusive lines 1..4)" in prompt
    assert inputs.source_files[0].content not in prompt
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
