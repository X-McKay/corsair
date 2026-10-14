"""Run one native agent and record its usage as ``contracts.AgentUsage``.

Every v2 agent stage calls ``run_recorded`` so status and telemetry mean the same thing everywhere:

- requests, tokens and tool calls come from the native ``RunUsage``, which the run fills in place, so a failed run
  still reports what it spent;
- a value the provider did not report stays None (unknown, never zero): token counts of 0 after at least one
  request mean the provider sent no usage, and a run that never reached the model reports no request count;
- the status says why there is no output: ``budget_exhausted`` (a native ``UsageLimits`` cap), ``output_invalid``
  (output retries spent) or ``provider_error`` (the model endpoint failed). Anything else propagates, since it is a
  defect or an infrastructure failure the caller must attribute itself.
"""
from __future__ import annotations

import time
from typing import Any, Literal

from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.models import Model
from pydantic_ai.usage import RunUsage, UsageLimits

from corsair.v2.contracts import AgentUsage

AgentName = Literal["grounding", "builder", "investigator", "control_prober", "exploit_prober", "reviewer"]


def model_label(model: Model | None) -> str | None:
    if model is None:
        return None
    name = getattr(model, "model_name", None)
    return name if isinstance(name, str) and name else None


def to_agent_usage(agent: AgentName, usage: RunUsage | None, *, model: Model | None = None,
                   wall_s: float | None = None, status: str = "ok") -> AgentUsage:
    """Map native usage onto the contract; missing or unreported values stay None."""
    if usage is None or usage.requests == 0:
        return AgentUsage(agent=agent, model=model_label(model), wall_s=wall_s, status=status,
                          tool_calls=None if usage is None else usage.tool_calls or None)
    reported = usage.input_tokens > 0 or usage.output_tokens > 0
    return AgentUsage(agent=agent, model=model_label(model), requests=usage.requests,
                      input_tokens=usage.input_tokens if reported else None,
                      output_tokens=usage.output_tokens if reported else None,
                      tool_calls=usage.tool_calls, wall_s=wall_s, status=status)


async def run_recorded(agent: Agent[Any, Any], name: AgentName, prompt: str, *, model: Model, deps: Any = None,
                       usage_limits: UsageLimits | None = None, **run_kwargs: Any) -> tuple[Any | None, AgentUsage]:
    """Run ``agent`` once and return (output or None, usage). ``run_kwargs`` go to ``Agent.run`` unchanged.

    ``model`` only labels the usage: the agent already holds its model from its factory, which is what a durable
    run resolves, so it is never swapped here.
    """
    usage, started, status, output = RunUsage(), time.monotonic(), "ok", None
    try:
        result = await agent.run(prompt, deps=deps, usage=usage, usage_limits=usage_limits, **run_kwargs)
        output = result.output
    except UsageLimitExceeded:
        status = "budget_exhausted"
    except ModelAPIError:
        status = "provider_error"
    except UnexpectedModelBehavior:
        status = "output_invalid"
    return output, to_agent_usage(name, usage, model=model, wall_s=time.monotonic() - started, status=status)
