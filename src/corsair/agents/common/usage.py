"""Run one native agent and record its usage as ``contracts.AgentUsage``.

Every v2 agent stage calls ``run_recorded`` so status and telemetry mean the same thing everywhere:

- requests, tokens and tool calls come from the native ``RunUsage``, which the run fills in place, so a failed run
  still reports what it spent;
- a value the provider did not report stays None (unknown, never zero): token counts of 0 after at least one
  request mean the provider sent no usage, and a run that never reached the model reports no request count;
- the parameters the run used come from the native objects (``model.settings`` merged under the agent's own
  model settings, the ``UsageLimits`` passed, the agent's retry settings) and the agent's ``agent.yaml`` metadata
  (``call_parameters``); ``retries`` counts the retry prompts in the run's message history;
- the status says why there is no output: ``budget_exhausted`` (a native ``UsageLimits`` cap), ``output_invalid``
  (output retries spent) or ``provider_error`` (the model endpoint failed). Anything else propagates, since it is a
  defect or an infrastructure failure the caller must attribute itself.
"""
from __future__ import annotations

import hashlib
import time
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic_ai import Agent
from pydantic_ai.agent.spec import AgentSpec
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.messages import ModelMessage, ModelRequest, RetryPromptPart
from pydantic_ai.models import Model
from pydantic_ai.usage import RunUsage, UsageLimits

from corsair.contracts import AgentUsage

AgentName = Literal["grounding", "builder", "investigator", "control_prober", "exploit_prober", "reviewer"]


def model_label(model: Model | None) -> str | None:
    if model is None:
        return None
    name = getattr(model, "model_name", None)
    return name if isinstance(name, str) and name else None


AGENTS_DIR = Path(__file__).resolve().parents[1]
"""Each v2 agent's package, ``agents/<name>/agent.yaml``, holds its spec and version metadata."""


@lru_cache(maxsize=None)
def spec_identity(agent: str) -> dict[str, str | None]:
    """prompt_version, config_version (from the spec's metadata) and the sha256 of the agent's ``agent.yaml``."""
    path = AGENTS_DIR / agent / "agent.yaml"
    if not path.is_file():
        return {"prompt_version": None, "config_version": None, "spec_sha256": None}
    meta = AgentSpec.from_file(path).metadata or {}
    return {"prompt_version": _text(meta.get("prompt_version")), "config_version": _text(meta.get("config_version")),
            "spec_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def model_parameters(model: Model | None, agent_settings: Any = None) -> dict[str, Any]:
    """Model id, endpoint host and sampling parameters from the model's native settings; unknown stays None.

    ``agent_settings`` (the agent's own static model settings, when a dict) override the model's, as at run time.
    A setting the request does not carry is None (the server's default, not known here); ``thinking`` is
    ``server_default`` when the settings are known and carry no thinking control.
    """
    host = None
    base_url = getattr(model, "base_url", None) if model is not None else None
    if isinstance(base_url, str) and base_url:
        host = urlsplit(base_url).hostname  # never the user info, path or query
    settings = getattr(model, "settings", None) if model is not None else None
    if settings is None and not isinstance(agent_settings, dict):
        return {"model": model_label(model), "provider_host": host, "temperature": None, "max_tokens": None,
                "thinking": None, "thinking_budget": None}
    merged = {**(settings or {}), **(agent_settings if isinstance(agent_settings, dict) else {})}
    extra = merged.get("extra_body") if isinstance(merged.get("extra_body"), dict) else {}
    template = extra.get("chat_template_kwargs") if isinstance(extra.get("chat_template_kwargs"), dict) else {}
    budget = _int(extra.get("thinking_token_budget"))
    if template.get("enable_thinking") is False:
        thinking = "disabled"
    elif budget is not None:
        thinking = "budget"
    elif merged.get("thinking") is not None:
        thinking = str(merged["thinking"])
    else:
        thinking = "server_default"
    temperature = merged.get("temperature")
    return {"model": model_label(model), "provider_host": host,
            "temperature": float(temperature) if isinstance(temperature, (int, float)) else None,
            "max_tokens": _int(merged.get("max_tokens")), "thinking": thinking, "thinking_budget": budget}


def call_parameters(name: str, model: Model | None, *, agent: Agent[Any, Any] | None = None,
                    usage_limits: UsageLimits | None = None) -> dict[str, Any]:
    """Every parameter an agent call ran with, as ``AgentUsage`` fields; what is not known here stays None.

    The agent's retry settings have no public accessor in PydanticAI, so they are read from its attributes when
    present and are None otherwise.
    """
    return {
        **model_parameters(model, getattr(agent, "model_settings", None) if agent is not None else None),
        "request_limit": _int(getattr(usage_limits, "request_limit", None)),
        "tool_calls_limit": _int(getattr(usage_limits, "tool_calls_limit", None)),
        "max_output_retries": _int(getattr(agent, "_max_output_retries", None)),
        "max_tool_retries": _int(getattr(agent, "_max_tool_retries", None)),
        **spec_identity(name),
    }


def count_retries(messages: Iterable[ModelMessage]) -> int:
    """Retry prompts (an invalid output or a failed tool call sent back to the model) in a run's history."""
    return sum(isinstance(part, RetryPromptPart) for message in messages if isinstance(message, ModelRequest)
               for part in message.parts)


def to_agent_usage(agent: AgentName, usage: RunUsage | None, *, model: Model | None = None,
                   wall_s: float | None = None, status: str = "ok", **parameters: Any) -> AgentUsage:
    """Map native usage onto the contract; missing or unreported values stay None. ``parameters`` are further
    ``AgentUsage`` fields (``call_parameters``, ``retries``)."""
    parameters = {"model": model_label(model), **parameters}
    if usage is None or usage.requests == 0:
        return AgentUsage(agent=agent, wall_s=wall_s, status=status,
                          tool_calls=None if usage is None else usage.tool_calls or None, **parameters)
    reported = usage.input_tokens > 0 or usage.output_tokens > 0
    return AgentUsage(agent=agent, requests=usage.requests,
                      input_tokens=usage.input_tokens if reported else None,
                      output_tokens=usage.output_tokens if reported else None,
                      tool_calls=usage.tool_calls, wall_s=wall_s, status=status, **parameters)


async def run_recorded(agent: Agent[Any, Any], name: AgentName, prompt: str, *, model: Model, deps: Any = None,
                       usage_limits: UsageLimits | None = None, **run_kwargs: Any) -> tuple[Any | None, AgentUsage]:
    """Run ``agent`` once and return (output or None, usage). ``run_kwargs`` go to ``Agent.run`` unchanged.

    ``model`` only labels the usage: the agent already holds its model from its factory, which is what a durable
    run resolves, so it is never swapped here.
    """
    usage, started, status, output, error, retries = RunUsage(), time.monotonic(), "ok", None, None, None
    try:
        result = await agent.run(prompt, deps=deps, usage=usage, usage_limits=usage_limits, **run_kwargs)
        output, retries = result.output, count_retries(result.all_messages())
    except UsageLimitExceeded as exc:
        status, error = "budget_exhausted", exc
    except ModelAPIError as exc:
        status, error = "provider_error", exc
    except UnexpectedModelBehavior as exc:
        status, error = "output_invalid", exc
    # A failed run's history is not returned here; the caller that captured it (chain.LocalOps) counts its retries.
    # ``model`` labels the call; the parameters come from the model the agent actually holds.
    actual = agent.model if isinstance(agent.model, Model) else model
    parameters = call_parameters(name, actual, agent=agent, usage_limits=usage_limits)
    del parameters["model"]
    recorded = to_agent_usage(name, usage, model=model if model_label(model) else actual,
                              wall_s=time.monotonic() - started, status=status, retries=retries, **parameters)
    if error is not None:  # keep the upstream detail so a failure stays attributable
        recorded = recorded.model_copy(update={"error": f"{type(error).__name__}: {error}"[:2_000]})
    return output, recorded
