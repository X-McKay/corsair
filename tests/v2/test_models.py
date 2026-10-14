"""Provider config: every agent mapped, explicit errors, native OpenAIChatModel with the carried-over settings."""
import asyncio
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from pydantic_ai.models.openai import OpenAIChatModel

from corsair.v2.models import AGENTS, ProviderConfig, agent_models, load_provider_config

LOCAL = Path(__file__).resolve().parents[2] / "config" / "v2" / "providers.local.json"


def _config(**profile):
    return {"profiles": {"p": {"base_url": "https://model.example/v1", "model_name": "m", **profile}},
            "agents": {agent: "p" for agent in AGENTS}}


def test_local_config_maps_every_agent_to_the_local_endpoint():
    config = load_provider_config(LOCAL)
    for agent in AGENTS:
        profile = config.profile(agent)
        assert profile.base_url == "https://llm.almckay.io/v1" and profile.model_name == "Qwen3.6-35B-A3B-NVFP4"
        assert profile.api_key_env is None


def test_models_are_native_and_carry_the_settings_without_any_request():
    async def build():
        async with agent_models(ProviderConfig.model_validate(_config(thinking_token_budget=2048))) as models:
            return models
    models = asyncio.run(build())
    assert set(models) == set(AGENTS)
    model = models["reviewer"]
    assert isinstance(model, OpenAIChatModel) and model.model_name == "m"
    assert model.settings == {"max_tokens": 8192, "parallel_tool_calls": False, "temperature": 0,
                              "extra_body": {"thinking_token_budget": 2048}}
    assert models["builder"] is model  # one client per profile


@pytest.mark.parametrize("change, message", [
    (lambda c: c["agents"].pop("reviewer"), "reviewer"),
    (lambda c: c["agents"].update(builder="missing"), "missing"),
    (lambda c: c["profiles"]["p"].update(base_url="http://model.example/v1"), "HTTPS"),
    (lambda c: c["profiles"]["p"].update(thinking="disabled", thinking_token_budget=10), "thinking"),
    (lambda c: c["profiles"]["p"].update(unknown=1), "unknown"),
])
def test_invalid_configs_are_explicit_errors(change, message):
    config = _config()
    change(config)
    with pytest.raises(ValidationError, match=message):
        ProviderConfig.model_validate(config)


def test_missing_credential_is_refused_before_any_client(monkeypatch, tmp_path):
    monkeypatch.delenv("CORSAIR_V2_TEST_KEY", raising=False)
    path = tmp_path / "p.json"
    path.write_text(json.dumps(_config(api_key_env="CORSAIR_V2_TEST_KEY")))

    async def build():
        async with agent_models(load_provider_config(path)):
            pass
    with pytest.raises(ValueError, match="CORSAIR_V2_TEST_KEY"):
        asyncio.run(build())
