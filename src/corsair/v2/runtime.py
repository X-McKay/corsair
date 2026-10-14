"""Native cognitive-stage runtime for Corsair v2.

This module does not create a custom model loop.  It invokes a constructed
PydanticAI ``Agent`` directly; in a Temporal workflow the agent's attached
``TemporalDurability`` turns supported model/capability work into native
activities.  Deterministic source capture, citation admission, and output
persistence stay outside the model trajectory.
"""
from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import Any
from uuid import uuid4

from pydantic import BaseModel
from pydantic_ai import Agent, capture_run_messages
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.messages import (
    WorkspaceRef as NativeWorkspaceRef,
)
from pydantic_ai.usage import RunUsage, UsageLimits

from .agents.dependencies import AgentDeps
from .agents.factory import build_agents, close_agents
from .agents.prompts import ROLES, render_public_input
from .agents.workspace import prepare_source_workspace
from .contracts import (
    AgentResult,
    AnalysisInput,
    AnalysisResult,
    ArtifactRef,
    Budget,
    Citation,
    OperatorConfig,
    SourceAssessment,
    SourceFile,
    SourceSnapshot,
    StageMetrics,
)
from .storage import Store

_USAGE_FIELDS = ("requests", "tool_calls", "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")
_TOKEN_FIELDS = {"input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"}
_AVAILABILITY = {"reported", "reported_zero", "not_reported", "not_applicable", "unknown"}


def _workflow_clock() -> tuple[float, str]:
    """Use the Temporal deterministic clock when available, otherwise monotonic time."""
    from temporalio import workflow
    if workflow.in_workflow():
        return workflow.now().timestamp(), "temporal_workflow_now_includes_native_activity_queue_and_execution"
    return perf_counter(), "perf_counter_direct_process"


def _usage_snapshot(usage: RunUsage | None) -> dict[str, Any]:
    if usage is None:
        return {field: 0 for field in _USAGE_FIELDS} | {"details": {}}
    return {field: int(getattr(usage, field, 0) or 0) for field in _USAGE_FIELDS} | {
        "details": dict(getattr(usage, "details", {}) or {})
    }


def _usage_delta(before: dict[str, Any], usage: RunUsage | None) -> dict[str, Any]:
    after = _usage_snapshot(usage)
    result = {field: max(0, int(after[field]) - int(before[field])) for field in _USAGE_FIELDS}
    # Details are provider-specific cumulative counters. A shared RunUsage
    # cannot reliably represent every detail as a delta, so retain both raw
    # post-run details and the conservative nonnegative observed difference.
    result["details"] = {
        key: max(0, int(value) - int(before["details"].get(key, 0)))
        for key, value in after["details"].items()
        if isinstance(value, int)
    }
    result["raw_after"] = after
    return result


def _metrics(
    *, role: str, model: str, started: float, clock: str, before: dict[str, Any], usage: RunUsage | None,
    status: str, error: str | None = None, trajectory: tuple[dict[str, Any], ...] = (), responses: tuple = (),
) -> StageMetrics:
    ended, end_clock = _workflow_clock()
    # A direct/external failure cannot make latency negative. Different clocks
    # only occur if a caller entered/leaves Temporal unexpectedly; expose that
    # fact rather than synthesizing a duration.
    elapsed = max(0.0, ended - started) if end_clock == clock else 0.0
    delta = _usage_delta(before, usage)
    availability: dict[str, str] = {}
    values: dict[str, int | None] = {}
    for field in _USAGE_FIELDS:
        value = int(delta[field])
        if field in _TOKEN_FIELDS:
            values[field] = value if value > 0 else None
            availability[field] = "reported" if value > 0 else "unknown"
        else:
            values[field] = value
            availability[field] = "reported" if value > 0 else "reported_zero"
    reasoning = None
    reason_key = next((key for key in ("reasoning_tokens", "thinking_tokens") if key in delta["details"]), None)
    if reason_key is not None and delta["details"][reason_key] > 0:
        reasoning = int(delta["details"][reason_key])
        availability["reasoning_tokens"] = "reported"
    else:
        availability["reasoning_tokens"] = "unknown"
    availability["cost_usd"] = "unknown"
    provider_usage = [(message.metadata or {}).get("corsair_usage_presence") for message in responses]
    provider_usage = [item for item in provider_usage if isinstance(item, dict)]
    for field in (*_TOKEN_FIELDS, "reasoning_tokens"):
        if not provider_usage:
            continue
        complete = (len(provider_usage) == delta["requests"] and
                    all(item.get("fields", {}).get(field) is True for item in provider_usage))
        if complete:
            value = int(delta.get(field, reasoning if field == "reasoning_tokens" else 0) or 0)
            availability[field] = "reported_zero" if value == 0 else "reported"
            if field == "reasoning_tokens":
                reasoning = value
            else:
                values[field] = value
        else:
            availability[field] = "not_reported"
            if field == "reasoning_tokens":
                reasoning = None
            else:
                values[field] = None
    if status != "completed" and delta["requests"] == 0:
        values["requests"] = None
        availability["requests"] = "unknown"
    # Keep the prior eval projection compatible while StageMetrics exposes the
    # typed map. No raw prompt/source/tool return content is retained here.
    usage_details = {
        "schema": "corsair.model-usage.v1",
        "raw_sdk_usage": delta["raw_after"],
        "details_delta": delta["details"],
        "field_availability": availability,
        "latency_clock": clock,
        "provider_usage": provider_usage,
    }
    return StageMetrics(
        role=role,
        model=model,
        latency_seconds=elapsed,
        requests=values["requests"],
        tool_calls=values["tool_calls"],
        input_tokens=values["input_tokens"],
        output_tokens=values["output_tokens"],
        cache_read_tokens=values["cache_read_tokens"],
        cache_write_tokens=values["cache_write_tokens"],
        reasoning_tokens=reasoning,
        field_availability=availability,
        usage_details=usage_details,
        status=status,  # type: ignore[arg-type]
        error=error,
        trajectory=trajectory,
    )


def _compact_trajectory(result: Any) -> tuple[dict[str, Any], ...]:
    """Expose only model/tool event kinds and names, never raw agent content."""
    events: list[dict[str, Any]] = []
    try:
        messages = result if isinstance(result, list) else result.all_messages()
    except Exception:  # noqa: BLE001 - foreign-library boundary: explicit failed/unknown outcome
        return ()
    for message in messages:
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, ToolReturnPart):
                    events.append({"kind": "tool_return", "tool": part.tool_name})
        elif isinstance(message, ModelResponse):
            events.append({"kind": "model_response", "model": message.model_name or "unknown"})
            for part in message.parts:
                if isinstance(part, ToolCallPart):
                    events.append({"kind": "tool_call", "tool": part.tool_name})
            for attempt in message.failed_attempts or ():
                events.append({
                    "kind": "model_failed_attempt",
                    "outcome": str(getattr(attempt, "outcome", "unknown")),
                    "model": str(getattr(attempt, "model_name", "unknown")),
                })
        if len(events) >= 128:
            events.append({"kind": "trajectory_truncated"})
            break
    return tuple(events)


def _agent_model_name(agent: Agent) -> str:
    model = getattr(agent, "model", None)
    value = getattr(model, "model_name", None)
    return str(value) if value else "unknown"


def _stage_status(error: BaseException) -> str:
    if isinstance(error, (UsageLimitExceeded, TimeoutError)) or "UsageLimit" in type(error).__name__:
        return "budget_exhausted"
    return "failed"


async def run_agent(
    agent: Agent,
    role: str,
    public_input: dict[str, Any],
    deps: AgentDeps,
    budget: Budget,
    usage: RunUsage | None = None,
) -> AgentResult:
    """Run one native agent with strict public input and native limits only.

    Apart from native agent activities (model/file/skill/planning dispatch when
    attached), this function performs no filesystem, store, database, or
    network I/O. Callers own artifact persistence and deterministic evidence
    admission. External cancellation intentionally propagates.
    """
    if role not in ROLES or not isinstance(agent, Agent):
        raise ValueError("A constructed agent and known role are required")
    if not isinstance(public_input, dict) or not isinstance(deps, AgentDeps) or not isinstance(budget, Budget):
        raise ValueError("public_input, AgentDeps, and Budget are required")  # noqa: TRY004 - invalid admission is consistently ValueError
    usage = usage if usage is not None else RunUsage()
    prompt = render_public_input(role, public_input)  # pure allowlist
    started, clock = _workflow_clock()
    before = _usage_snapshot(usage)
    model = _agent_model_name(agent)
    native_ref = None if deps.workspace_ref is None else NativeWorkspaceRef(
        provider=deps.workspace_ref.provider, id=deps.workspace_ref.id
    )
    limits = UsageLimits(
        request_limit=budget.request_limit,
        tool_calls_limit=budget.tool_calls_limit,
        input_tokens_limit=budget.input_tokens_limit,
        output_tokens_limit=budget.output_tokens_limit,
        total_tokens_limit=budget.input_tokens_limit + budget.output_tokens_limit,
    )
    captured_messages = []
    try:
        # Awaiting a native durable agent in a workflow schedules its SDK-owned
        # activities. The explicit stable IDs are passed at construction.
        with capture_run_messages() as captured_messages:
            async with asyncio.timeout(budget.stage_timeout_seconds):
                result = await agent.run(
                    prompt,
                    deps=deps,
                    run_id=f"{deps.run_id}:{deps.stage_id}",
                    usage_limits=limits,
                    usage=usage,
                    workspace=native_ref,
                )
        output = result.output
        if not isinstance(output, BaseModel):
            raise TypeError("Native structured output did not return a Pydantic model")
        return AgentResult(
            role=role,
            output=output.model_dump(mode="json"),
            metrics=_metrics(
                role=role, model=model, started=started, clock=clock, before=before, usage=result.usage,
                status="completed", trajectory=_compact_trajectory(result),
                responses=tuple(m for m in result.all_messages() if isinstance(m, ModelResponse)),
            ),
        )
    except asyncio.CancelledError:
        raise
    except Exception as error:
        logging.getLogger(__name__).debug("Native stage failed; debug logs may contain sensitive provider details", exc_info=True)
        # Provider/budget failures are a stage result, never a fake output. The
        # compact exception type avoids raw provider/source/credential leakage.
        # Error bodies from arbitrary providers can contain prompt/key echoes.
        # Keep only the exception class; raw API diagnostics are not telemetry.
        message = type(error).__name__
        return AgentResult(
            role=role,
            output=None,
            metrics=_metrics(
                role=role, model=model, started=started, clock=clock, before=before, usage=usage,
                status=_stage_status(error), error=message,
                trajectory=_compact_trajectory(captured_messages),
                responses=tuple(m for m in captured_messages if isinstance(m, ModelResponse)),
            ),
        )


def _capture_analysis_input(inputs: AnalysisInput, store: Store) -> SourceSnapshot:
    """Publish exact public source bytes as immutable artifacts without host execution."""
    files: list[SourceFile] = []
    for path, text in sorted(inputs.files.items()):
        data = text.encode("utf-8")
        files.append(SourceFile(path=path, artifact=store.put(data)))
    value = {
        "schema_version": "source-v2",
        "repository": "analysis-input",
        "commit": None,
        "tree": None,
        "files": [{"path": item.path, "artifact": item.artifact.model_dump(mode="json"), "mode": item.mode} for item in files],
        "skipped": [],
    }
    manifest = store.put_json(value)
    return SourceSnapshot(repository="analysis-input", files=tuple(files), manifest=manifest)


def _valid_citation(citation: Citation, inputs: AnalysisInput) -> bool:
    text = inputs.files.get(citation.path)
    if text is None:
        return False
    count = len(text.splitlines())
    return count > 0 and citation.start_line <= citation.end_line <= count


async def analyze_case(inputs: AnalysisInput, config: OperatorConfig, *, attempt_id: str | None = None) -> AnalysisResult:
    """Run the production source-only analysis role over immutable public bytes.

    A result is a source classification prediction only. This entry point never
    executes captured source or turns a model result into a security verdict.
    """
    if not isinstance(inputs, AnalysisInput) or not isinstance(config, OperatorConfig):
        raise ValueError("AnalysisInput and OperatorConfig are required")  # noqa: TRY004 - invalid admission is consistently ValueError
    store = Store(config.storage_root)
    snapshot = _capture_analysis_input(inputs, store)
    ref = prepare_source_workspace(snapshot, config)
    deps = AgentDeps(
        run_id=attempt_id or "analysis-" + uuid4().hex,
        stage_id="analysis",
        source_manifest=snapshot.manifest,
        workspace_ref=ref,
    )
    agents = {}
    try:
        agents = build_agents(config)
        agent = agents["analysis"]
        result = await run_agent(
            agent,
            "analysis",
            {"concern": inputs.concern, "language": inputs.language, "framework": inputs.framework,
             "cwe": list(inputs.cwe), "files": inputs.files if sum(len(text.encode()) for text in inputs.files.values()) <= 32768
             else sorted(inputs.files)},
            deps,
            config.budget,
        )
        assessment = SourceAssessment.model_validate(result.output) if result.output is not None else None
        if assessment is not None and not all(_valid_citation(item, inputs) for item in assessment.citations):
            metrics = result.metrics.model_copy(update={
                "status": "failed",
                "error": "CitationAdmissionError: assessment cites a path or line range absent from captured source",
            })
            return AnalysisResult(assessment=None, metrics=metrics)
        output_ref: ArtifactRef | None = None
        if assessment is not None:
            output_ref = store.put_json(assessment.model_dump(mode="json"))
        return AnalysisResult(assessment=assessment, metrics=result.metrics, output_ref=output_ref)
    finally:
        # Content-addressed source copies are shared read-only by concurrent
        # trials. Deleting one here could interrupt a different live trial.
        await close_agents(agents)
        store.close()


__all__ = ["analyze_case", "prepare_source_workspace", "run_agent"]
