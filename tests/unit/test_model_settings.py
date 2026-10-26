from __future__ import annotations

import pytest

from corsair.adapters.inference.models import model_for_role
from corsair.agents.resources import AgentSpec, load_agent_spec, prompt_text
from corsair.settings import ModelSettings


def test_gemini_role_models_remain_plain_native_ids():
    settings = ModelSettings(producer="gemini-2.5-flash", auditor="gemini-2.5-pro")

    assert model_for_role(settings, "producer") == "gemini-2.5-flash"
    assert model_for_role(settings, "auditor") == "gemini-2.5-pro"


def test_gemini_rejects_litellm_endpoint_configuration():
    with pytest.raises(ValueError, match="api_base"):
        model_for_role(
            ModelSettings(connector="gemini", api_base="https://provider.example/v1"), "producer"
        )


def test_litellm_model_uses_only_configured_endpoint_controls(monkeypatch):
    captured: dict[str, object] = {}

    class FakeLiteLlm:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    import google.adk.models as adk_models

    # Patch the module namespace directly: getattr-based patching would first
    # trigger ADK's lazy LiteLlm import, which needs the optional providers
    # extra although this test never constructs the real class.
    monkeypatch.setitem(vars(adk_models), "LiteLlm", FakeLiteLlm)
    value = model_for_role(
        ModelSettings(
            connector="litellm",
            producer="hosted_vllm/example",
            api_base="https://provider.example/v1",
            request_timeout_seconds=17,
            extra_body={"reasoning_effort": "low"},
        ),
        "producer",
    )

    assert isinstance(value, FakeLiteLlm)
    assert captured == {
        "model": "hosted_vllm/example",
        "api_base": "https://provider.example/v1",
        "timeout": 17,
        "num_retries": 0,
        "extra_body": {"reasoning_effort": "low"},
    }
    assert "api_key" not in captured


def test_litellm_without_providers_extra_names_the_project_remedy(monkeypatch):
    import sys

    import google.adk.models as adk_models

    monkeypatch.delitem(vars(adk_models), "LiteLlm", raising=False)
    # A None entry makes ADK's lazy import fail exactly as a missing extra does.
    monkeypatch.setitem(sys.modules, "google.adk.models.lite_llm", None)

    with pytest.raises(ImportError, match="providers extra") as raised:
        model_for_role(ModelSettings(connector="litellm", producer="hosted_vllm/x"), "producer")

    assert "just sync" in str(raised.value)
    assert isinstance(raised.value.__cause__, ImportError)


def test_litellm_openai_route_is_rejected_for_the_tool_using_producer():
    """The producer uses tools; ADK pairs its schema with them, and a LiteLLM
    'openai/' route backed by vLLM guided-decodes and blocks tool calls. The
    combination is rejected at config time rather than silently voiding a run."""
    with pytest.raises(ValueError, match="guided decoding"):
        ModelSettings(connector="litellm", producer="openai/qwen")


def test_litellm_openai_route_is_allowed_for_the_tool_free_auditor():
    """The auditor has no tools, so a schema-only 'openai/' route is safe for it."""
    settings = ModelSettings(
        connector="litellm", producer="hosted_vllm/qwen", auditor="openai/qwen"
    )
    assert settings.auditor == "openai/qwen"


def test_agent_specs_are_validated_resource_metadata_with_manifest_tools_field():
    producer = load_agent_spec("producer")
    auditor = load_agent_spec("auditor")

    assert producer.source_tools == ["read_file", "list_files"]
    assert producer.loader_tools == ["load_skill", "load_skill_resource"]
    assert producer.tools == [*producer.source_tools, *producer.loader_tools]
    # The auditor's procedure is preloaded; it declares no tool, loader or otherwise.
    assert auditor.tools == auditor.source_tools == auditor.loader_tools == []
    assert producer.runtime_skills == ["source-grounding"]
    assert auditor.runtime_skills == ["semantic-review"]
    assert producer.llm_call_limit is None
    assert auditor.llm_call_limit == 1
    assert producer.loader_call_limit == 4
    assert auditor.loader_call_limit == 0
    assert producer.risk_path == auditor.risk_path == "corsair.policies:risk.md"
    assert producer.schema_ref == "corsair.contracts.ProducerDecision"
    assert auditor.schema_ref == "corsair.contracts.AuditResult"
    assert "Return one structured ProducerDecision" in prompt_text("producer")
    assert "outcome-blind" in prompt_text("auditor")


def test_agent_spec_rejects_unknown_metadata_fields():
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        AgentSpec.model_validate(
            {
                "name": "auditor",
                "contract_version": "corsair.agent/2",
                "execution_class": "durable",
                "governance_tier": "review",
                "risk_path": "risk",
                "tools": [],
                "source_tools": [],
                "loader_tools": [],
                "runtime_skills": ["semantic-review"],
                "loader_call_limit": 0,
                "llm_call_limit": 1,
                "instruction_resource": "resource",
                "schema_ref": "corsair.contracts.AuditResult",
                "model": "must-not-be-declared-here",
            }
        )


def _auditor_spec(**overrides: object) -> dict[str, object]:
    spec: dict[str, object] = {
        "name": "auditor",
        "contract_version": "corsair.agent/2",
        "execution_class": "durable",
        "governance_tier": "review",
        "risk_path": "risk",
        "tools": [],
        "source_tools": [],
        "loader_tools": [],
        "runtime_skills": ["semantic-review"],
        "loader_call_limit": 0,
        "llm_call_limit": 1,
        "instruction_resource": "resource",
        "schema_ref": "corsair.contracts.AuditResult",
    }
    return {**spec, **overrides}


def test_agent_spec_admits_the_tool_free_auditor():
    assert AgentSpec.model_validate(_auditor_spec()).tools == []


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {
                "tools": ["load_skill", "load_skill_resource"],
                "loader_tools": ["load_skill", "load_skill_resource"],
                "loader_call_limit": 4,
            },
            "auditor loader_tools must exactly equal \\[\\]",
        ),
        ({"loader_call_limit": 2}, "positive exactly when loader tools exist"),
        ({"tools": ["read_file"], "source_tools": ["read_file"]}, "must not expose any tools"),
    ],
)
def test_agent_spec_rejects_any_auditor_tool(overrides: dict[str, object], message: str):
    with pytest.raises(ValueError, match=message):
        AgentSpec.model_validate(_auditor_spec(**overrides))


def test_agent_spec_still_requires_the_producer_loaders():
    producer = load_agent_spec("producer").model_dump(mode="json")
    with pytest.raises(ValueError, match="producer loader_tools must exactly equal"):
        AgentSpec.model_validate(
            {**producer, "tools": ["read_file", "list_files"], "loader_tools": []}
        )
    with pytest.raises(ValueError, match="positive exactly when loader tools exist"):
        AgentSpec.model_validate({**producer, "loader_call_limit": 0})
