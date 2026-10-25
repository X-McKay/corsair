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

    monkeypatch.setattr(adk_models, "LiteLlm", FakeLiteLlm, raising=False)
    value = model_for_role(
        ModelSettings(
            connector="litellm",
            producer="openai/example",
            api_base="https://provider.example/v1",
            request_timeout_seconds=17,
            extra_body={"reasoning_effort": "low"},
        ),
        "producer",
    )

    assert isinstance(value, FakeLiteLlm)
    assert captured == {
        "model": "openai/example",
        "api_base": "https://provider.example/v1",
        "timeout": 17,
        "num_retries": 0,
        "extra_body": {"reasoning_effort": "low"},
    }
    assert "api_key" not in captured


def test_agent_specs_are_validated_resource_metadata_with_manifest_tools_field():
    producer = load_agent_spec("producer")
    auditor = load_agent_spec("auditor")

    assert producer.source_tools == ["read_file", "list_files"]
    assert producer.loader_tools == ["load_skill", "load_skill_resource"]
    assert producer.tools == [*producer.source_tools, *producer.loader_tools]
    assert auditor.source_tools == []
    assert auditor.loader_tools == ["load_skill", "load_skill_resource"]
    assert auditor.tools == auditor.loader_tools
    assert producer.runtime_skills == ["source-grounding"]
    assert auditor.runtime_skills == ["semantic-review"]
    assert producer.llm_call_limit is None
    assert auditor.llm_call_limit == 2
    assert producer.loader_call_limit == auditor.loader_call_limit == 4
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
                "tools": ["load_skill", "load_skill_resource"],
                "source_tools": [],
                "loader_tools": ["load_skill", "load_skill_resource"],
                "runtime_skills": ["semantic-review"],
                "loader_call_limit": 4,
                "llm_call_limit": 2,
                "instruction_resource": "resource",
                "schema_ref": "corsair.contracts.AuditResult",
                "model": "must-not-be-declared-here",
            }
        )
