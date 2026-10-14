"""Native Temporal runtime for the Corsair v2 deterministic coordinator.

The one durable workflow delegates Corsair's state-changing business operations
through narrow named activities.  Cognitive stages intentionally remain regular
``Agent.run`` calls *inside* that workflow: ``TemporalDurability`` turns their
model and tool operations into the SDK's own fine-grained activities.  There is
no opaque ``run agent`` Corsair activity.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import signal
from collections.abc import Callable, Mapping
from contextlib import suppress
from datetime import timedelta
from pathlib import Path
from typing import Any

from pydantic_ai.durable_exec.temporal import PydanticAIPlugin, PydanticAIWorkflow
from temporalio import activity, workflow
from temporalio.client import Client, WorkflowHistory
from temporalio.common import RetryPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import ApplicationError
from temporalio.worker import Replayer, Worker

with workflow.unsafe.imports_passed_through():
    # SDK/model/manifest construction belongs to worker boot. Re-importing
    # these modules inside a workflow would re-read package YAML and reset
    # native agent registrations. All I/O methods remain activity-side only.
    from .agents import AgentDeps, build_agents
    from .config import safe_error
    from .contracts import AgentResult, OperatorConfig, RunResult, RunSpec, Verdict
    from .engine import Services, coordinate, episode_input, execution_identity
    from .episode import Episode, EpisodeInput, StageEnvelope
    from .temporal_boot import BINDINGS, Binding

WORKFLOW_NAME = "corsair.run.v2"
WORKFLOW_ID_PREFIX = "corsair-v2/"
PHASE_QUERY = "phase"
STOP_SIGNAL = "request_stop"


def task_queue(config: OperatorConfig) -> str:
    """Isolate different builds, prompts, providers, and policies using native queues."""
    return config.task_queue + "." + execution_identity(config)


async def connect(config: OperatorConfig) -> Client:
    key = os.environ.get(config.temporal_api_key_env) if config.temporal_api_key_env else None
    if config.temporal_api_key_env and not key:
        raise ValueError("Missing configured Temporal API key")
    return await Client.connect(config.temporal_address, namespace=config.temporal_namespace,
                                tls=config.temporal_tls, api_key=key, plugins=[PydanticAIPlugin()])

# Persisted activity type names.  Names are compatibility data for histories,
# therefore all worker construction goes through this single registry.
ACTIVITY_ADMIT = "corsair.v2.admit"
ACTIVITY_PREPARE_STAGE = "corsair.v2.prepare_stage"
ACTIVITY_RECORD_STAGE = "corsair.v2.record_stage"
ACTIVITY_FREEZE_PAIR = "corsair.v2.freeze_pair"
ACTIVITY_REVIEW_VALID = "corsair.v2.review_valid"
ACTIVITY_EXECUTE_REVISION = "corsair.v2.execute_revision"
ACTIVITY_APPLY_REPAIR = "corsair.v2.apply_repair"
ACTIVITY_REVISE_PLAN = "corsair.v2.revise_plan"
ACTIVITY_FINISH = "corsair.v2.finish"
ACTIVITY_RECONCILE = "corsair.v2.reconcile"

_ROLES = ("analysis", "investigator", "control_author", "exploit_author", "validity", "repair")
_EFFECT_ATTEMPTS = RetryPolicy(maximum_attempts=1)
_READONLY_ATTEMPTS = RetryPolicy(maximum_attempts=2)
_RESULT_TYPES = {
    ACTIVITY_ADMIT: Episode, ACTIVITY_PREPARE_STAGE: StageEnvelope,
    ACTIVITY_RECORD_STAGE: Episode, ACTIVITY_FREEZE_PAIR: Episode,
    ACTIVITY_REVIEW_VALID: bool, ACTIVITY_EXECUTE_REVISION: Episode,
    ACTIVITY_APPLY_REPAIR: Episode, ACTIVITY_REVISE_PLAN: Episode,
    ACTIVITY_FINISH: RunResult, ACTIVITY_RECONCILE: list[dict[str, Any]],
}


def workflow_id(request_id: str) -> str:
    """Return the fixed, path-safe Temporal identifier for one logical request."""
    if not isinstance(request_id, str) or not request_id:
        raise ValueError("A nonempty request_id is required")
    return WORKFLOW_ID_PREFIX + hashlib.sha256(request_id.encode("utf-8")).hexdigest()


def _validate_agents(agents: Mapping[str, Any]) -> dict[str, Any]:
    """Reject an incomplete or renamed durable worker inventory before polling."""
    if set(agents) != set(_ROLES):
        raise ValueError("Temporal workers require exactly the six admitted v2 role agents")
    checked = dict(agents)
    for role, agent in checked.items():
        expected = f"corsair.v2.{role}.v1"
        if getattr(agent, "name", None) != expected:
            raise ValueError(f"Temporal agent identity for {role!r} must remain {expected!r}")
    return checked


def _timeouts(config: OperatorConfig) -> tuple[timedelta, timedelta, timedelta]:
    """Derive bounded activity timeouts once at worker boot, never in a workflow."""
    stage = timedelta(seconds=config.budget.stage_timeout_seconds)
    # Source capture and result publication are bounded local operations but can
    # need more than a single model stage on a large permitted source tree.
    effect = timedelta(seconds=min(config.budget.episode_timeout_seconds, 600))
    readonly = timedelta(seconds=min(max(30, config.budget.stage_timeout_seconds), 180))
    return stage, effect, readonly


class TemporalPorts:
    """The deterministic coordinator's Temporal-only port implementation.

    The object is ephemeral workflow code.  It contains no provider, store,
    OpenShell client, file handle, or configuration I/O object.  Pydantic agents
    were constructed at worker boot and are references used solely by the
    PydanticAI plugin's registered native activities.
    """

    def __init__(self, owner: Any, agents: Mapping[str, Any], *, stage_timeout: timedelta,
                 effect_timeout: timedelta, readonly_timeout: timedelta):
        self._owner = owner
        self._agents = agents
        self._stage_timeout = stage_timeout
        self._effect_timeout = effect_timeout
        self._readonly_timeout = readonly_timeout

    def now(self) -> float:
        # Temporal's workflow clock is replay-safe.  This value is recorded in
        # history rather than sampled from the host wall/monotonic clock.
        return workflow.now().timestamp()

    def progress(self, phase: str) -> None:
        self._owner._phase = phase
        self._raise_if_stop_requested()

    def _raise_if_stop_requested(self) -> None:
        # A graceful signal is deliberately observed only at command boundaries.
        # External cancellation still interrupts an in-flight native model/tool
        # activity through Temporal's normal cancellation propagation.
        if self._owner._stop_requested:
            raise asyncio.CancelledError("corsair graceful stop requested at a safe point")

    async def _effect(self, name: str, *args: Any) -> Any:
        self._raise_if_stop_requested()
        native = name == ACTIVITY_EXECUTE_REVISION
        return await workflow.execute_activity(
            name,
            args=args,
            result_type=_RESULT_TYPES[name],
            start_to_close_timeout=timedelta(seconds=args[0].budget.episode_timeout_seconds) if native else self._effect_timeout,
            heartbeat_timeout=timedelta(seconds=30) if native else None,
            cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
            retry_policy=_EFFECT_ATTEMPTS,
        )

    async def _readonly(self, name: str, *args: Any) -> Any:
        self._raise_if_stop_requested()
        return await workflow.execute_activity(
            name,
            args=args,
            result_type=_RESULT_TYPES[name],
            start_to_close_timeout=self._readonly_timeout,
            retry_policy=_READONLY_ATTEMPTS,
        )

    async def admit(self, input: EpisodeInput) -> Episode:
        # Admission captures immutable input/source state.  It owns a durable
        # ledger idempotency record, but is still a one-attempt effect.
        return await self._effect(ACTIVITY_ADMIT, input)

    async def prepare_stage(self, episode: Episode, role: str) -> StageEnvelope:
        return await self._effect(ACTIVITY_PREPARE_STAGE, episode, role)

    async def cognitive(self, envelope: StageEnvelope) -> AgentResult:
        self._raise_if_stop_requested()
        # Deliberately *not* workflow.execute_activity(...): the regular agent
        # carries TemporalDurability, so this emits the native model/tool/workspace
        # activities registered by PydanticAIPlugin at worker boot.
        with workflow.unsafe.imports_passed_through():
            from .runtime import run_agent

        return await run_agent(
            self._agents[envelope.role],
            envelope.role,
            envelope.public_input,
            AgentDeps.model_validate(envelope.deps),
            envelope.budget,
        )

    async def record_stage(self, episode: Episode, envelope: StageEnvelope,
                           result: AgentResult) -> Episode:
        return await self._effect(ACTIVITY_RECORD_STAGE, episode, envelope, result)

    async def freeze_pair(self, episode: Episode) -> Episode:
        return await self._effect(ACTIVITY_FREEZE_PAIR, episode)

    async def review_valid(self, episode: Episode) -> bool:
        return await self._readonly(ACTIVITY_REVIEW_VALID, episode)

    async def revise_plan(self, episode: Episode) -> Episode:
        return await self._effect(ACTIVITY_REVISE_PLAN, episode)

    async def execute_revision(self, episode: Episode, revision: str) -> Episode:
        # Native OpenShell command effects are intentionally one attempt.
        return await self._effect(ACTIVITY_EXECUTE_REVISION, episode, revision)

    async def apply_repair(self, episode: Episode) -> Episode:
        return await self._effect(ACTIVITY_APPLY_REPAIR, episode)

    async def finish(self, episode: Episode, verdict=None, duration_seconds: float = 0.0) -> RunResult:
        return await self._effect(ACTIVITY_FINISH, episode, verdict, duration_seconds)

    async def reconcile(self, run_id: str) -> list[dict[str, Any]]:
        # Reconciliation reads the same identity before attempting its bounded
        # cleanup actions; retry is safe only for that identity-aware operation.
        return await self._readonly(ACTIVITY_RECONCILE, run_id)


@workflow.defn(name=WORKFLOW_NAME)
class CorsairRunWorkflow(PydanticAIWorkflow):
    __pydantic_ai_agents__ = ()

    def __init__(self) -> None:
        self._phase = "new"
        self._stop_requested = False

    @workflow.run
    async def run(self, input: EpisodeInput) -> RunResult:
        binding = BINDINGS.get(input.config_sha256)
        if binding is None or input.build_sha256 != binding.build_sha256:
            raise ValueError("Queued episode identity does not match this worker configuration/build")
        ports = TemporalPorts(self, binding.agents, stage_timeout=binding.stage_timeout,
                              effect_timeout=binding.effect_timeout, readonly_timeout=binding.readonly_timeout)
        try:
            async with asyncio.timeout(binding.episode_timeout.total_seconds()):
                return await coordinate(input, ports)
        except (asyncio.CancelledError, TimeoutError) as error:
            self._phase = "cancellation_reconciliation"
            try:
                await asyncio.shield(workflow.execute_activity(
                    ACTIVITY_RECONCILE, input.spec.request_id,
                    start_to_close_timeout=binding.readonly_timeout,
                    retry_policy=_READONLY_ATTEMPTS,
                    cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
                ))
            except BaseException:  # noqa: BLE001 - foreign-library boundary: explicit failed/unknown outcome
                # Retain the cancellation even if cleanup observation is lost.
                workflow.logger.warning("Cancellation reconciliation did not complete")
            if isinstance(error, TimeoutError):
                raise ApplicationError("Whole-episode workload budget exhausted", type="CorsairEpisodeTimeout", non_retryable=True) from error
            raise

    @workflow.query(name=PHASE_QUERY)
    def phase(self) -> dict[str, Any]:
        return {"phase": self._phase, "stop_requested": self._stop_requested}

    @workflow.signal(name=STOP_SIGNAL)
    def request_stop(self) -> None:
        self._stop_requested = True


def create_workflow(config: OperatorConfig, agents: Mapping[str, Any] | None = None) -> type:
    """Register an immutable boot binding before constructing Worker/Replayer."""
    durable_agents = _validate_agents(agents if agents is not None else build_agents(config, durable=True))
    identity = execution_identity(config)
    build = __import__("corsair.v2.config", fromlist=["build_identity"]).build_identity()["code_sha256"]
    stage, effect, readonly = _timeouts(config)
    if BINDINGS and identity not in BINDINGS:
        raise ValueError("Use a separate worker/replay process for each immutable configuration and build")
    BINDINGS[identity] = Binding(durable_agents, build, stage, effect, readonly,
                               timedelta(seconds=config.budget.episode_timeout_seconds))
    CorsairRunWorkflow.__pydantic_ai_agents__ = tuple(durable_agents[r] for r in _ROLES)
    return CorsairRunWorkflow


def activity_handlers(config: OperatorConfig, services: Services | None = None) -> tuple[Services, list[Callable[..., Any]]]:
    """Build worker-local named business activities around real ``Services``.

    ``services`` is only a construction seam for a native Temporal fixture; the
    production worker always supplies ``None`` and therefore creates the real
    v2 service.  No model/agent call is registered here.
    """
    if not isinstance(config, OperatorConfig):
        raise ValueError("A v2 OperatorConfig is required")  # noqa: TRY004 - invalid admission is consistently ValueError
    bound = services or Services(config)

    @activity.defn(name=ACTIVITY_ADMIT)
    async def admit(input: EpisodeInput) -> Episode:
        return await bound.admit(input)

    @activity.defn(name=ACTIVITY_PREPARE_STAGE)
    async def prepare_stage(episode: Episode, role: str) -> StageEnvelope:
        return await bound.prepare_stage(episode, role)

    @activity.defn(name=ACTIVITY_RECORD_STAGE)
    async def record_stage(episode: Episode, envelope: StageEnvelope, result: AgentResult) -> Episode:
        return await bound.record_stage(episode, envelope, result)

    @activity.defn(name=ACTIVITY_FREEZE_PAIR)
    async def freeze_pair(episode: Episode) -> Episode:
        return await bound.freeze_pair(episode)

    @activity.defn(name=ACTIVITY_REVIEW_VALID)
    async def review_valid(episode: Episode) -> bool:
        return await bound.review_valid(episode)

    @activity.defn(name=ACTIVITY_EXECUTE_REVISION)
    async def execute_revision(episode: Episode, revision: str) -> Episode:
        async def heartbeat() -> None:
            while True:
                activity.heartbeat({"run_id": episode.run_id, "revision": revision})
                await asyncio.sleep(5)
        pulse = asyncio.create_task(heartbeat())
        try:
            return await bound.execute_revision(episode, revision)
        finally:
            pulse.cancel()
            with suppress(asyncio.CancelledError):
                await pulse

    @activity.defn(name=ACTIVITY_APPLY_REPAIR)
    async def apply_repair(episode: Episode) -> Episode:
        return await bound.apply_repair(episode)

    @activity.defn(name=ACTIVITY_REVISE_PLAN)
    async def revise_plan(episode: Episode) -> Episode:
        return await bound.revise_plan(episode)

    @activity.defn(name=ACTIVITY_FINISH)
    async def finish(episode: Episode, verdict: Verdict | None = None, duration_seconds: float = 0.0) -> RunResult:
        return await bound.finish(episode, verdict, duration_seconds)

    @activity.defn(name=ACTIVITY_RECONCILE)
    async def reconcile(run_id: str) -> list[dict[str, Any]]:
        # A cancellation first records the identity-specific pending observation
        # in the worker ledger, then invokes the real reconciler.  This is not a
        # cleanup success claim.
        try:
            await asyncio.to_thread(
                bound.store.event,
                run_id,
                "temporal.cleanup_pending",
                {"run_id": run_id, "reason": "workflow_cancelled"},
                "temporal.cleanup_pending",
            )
        except ValueError:
            # Cancellation can arrive before admission has created the ledger;
            # the workflow remains cancelled and no phantom record is created.
            pass
        return await bound.reconcile(run_id)

    return bound, [
        admit,
        prepare_stage,
        record_stage,
        freeze_pair,
        review_valid,
        execute_revision,
        apply_repair,
        revise_plan,
        finish,
        reconcile,
    ]


async def run_worker(config: OperatorConfig) -> None:
    """Run one real worker until SIGINT/SIGTERM requests graceful shutdown."""
    if not isinstance(config, OperatorConfig):
        raise ValueError("A v2 OperatorConfig is required")  # noqa: TRY004 - invalid admission is consistently ValueError
    # Agent construction validates the exact admitted provider/profile before
    # this worker polls or effects queued work.
    agents = _validate_agents(build_agents(config, durable=True))
    workflow_class = create_workflow(config, agents)
    services, activities = activity_handlers(config)
    client = await connect(config)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    installed: list[signal.Signals] = []
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stop.set)
            installed.append(signum)
        except (NotImplementedError, RuntimeError):
            # Non-main-thread test workers may not install signal handlers.  The
            # caller still controls task cancellation explicitly in that mode.
            pass
    try:
        async with Worker(
            client,
            task_queue=task_queue(config),
            workflows=[workflow_class],
            activities=activities,
            workflow_failure_exception_types=[Exception],
            # PydanticAIPlugin comes from the Client and registers native agent
            # activities through __pydantic_ai_agents__; never add AgentPlugin.
        ):
            # Worker.__aenter__ already starts its run loop; calling run() a
            # second time is an SDK error, not a second supervision mechanism.
            await stop.wait()
    finally:
        for signum in installed:
            loop.remove_signal_handler(signum)
        from .agents.factory import close_agents
        await close_agents(agents)
        await services.aclose()


async def submit(spec: RunSpec, config: OperatorConfig, wait: bool = False) -> dict[str, Any] | RunResult:
    """Start the one identity-bound workflow, optionally await its typed result."""
    if not isinstance(spec, RunSpec) or not isinstance(config, OperatorConfig):
        raise ValueError("submit requires a v2 RunSpec and OperatorConfig")  # noqa: TRY004 - invalid admission is consistently ValueError
    input = episode_input(spec, config)
    client = await connect(config)
    handle = await client.start_workflow(
        WORKFLOW_NAME,
        input,
        id=workflow_id(spec.request_id),
        task_queue=task_queue(config),
        result_type=RunResult,
        execution_timeout=timedelta(seconds=config.budget.episode_timeout_seconds + config.budget.stage_timeout_seconds
                                    + config.sandbox.command_timeout_seconds + 120),
        id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
    )
    if wait:
        return await handle.result()
    return {
        "workflow_id": handle.id,
        "run_id": handle.run_id,
        "request_id": spec.request_id,
        "config_sha256": input.config_sha256,
        "build_sha256": input.build_sha256,
        "status": "started",
    }


async def status(run_id: str, config: OperatorConfig) -> dict[str, Any]:
    """Describe a workflow and attempt its read-only phase query without faking it."""
    if not isinstance(run_id, str) or not run_id or not isinstance(config, OperatorConfig):
        raise ValueError("status requires a nonempty workflow id and v2 OperatorConfig")
    client = await connect(config)
    handle = client.get_workflow_handle(run_id)
    description = await handle.describe()
    value: dict[str, Any] = {
        "workflow_id": description.id,
        "run_id": description.run_id,
        "status": str(description.status.name).lower(),
        "task_queue": description.task_queue,
    }
    try:
        value["phase"] = await handle.query(PHASE_QUERY)
        value["phase_query"] = "available"
    except Exception as error:  # noqa: BLE001 - foreign-library boundary: explicit failed/unknown outcome
        # A query requires a compatible worker for an open execution.  Closed
        # result/ledger state is not fabricated as a successful query.
        value["phase"] = None
        value["phase_query"] = "unavailable"
        value["phase_query_error"] = safe_error(error, config)
    return value


async def cancel(run_id: str, config: OperatorConfig, graceful: bool = False) -> dict[str, Any]:
    """Signal a safe-point stop or request native Temporal cancellation."""
    if not isinstance(run_id, str) or not run_id or not isinstance(config, OperatorConfig):
        raise ValueError("cancel requires a nonempty workflow id and v2 OperatorConfig")
    client = await connect(config)
    handle = client.get_workflow_handle(run_id)
    if graceful:
        await handle.signal(STOP_SIGNAL)
        return {"workflow_id": run_id, "mode": "graceful_signal", "signal": STOP_SIGNAL}
    await handle.cancel()
    return {"workflow_id": run_id, "mode": "native_cancel"}


def _private_history_path(path: Path | str) -> Path:
    value = Path(path).expanduser().absolute()
    value.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if value.exists() or value.is_symlink():
        raise ValueError("History export destination must be a new non-symlink private file")
    return value


async def export_history(run_id: str, config: OperatorConfig, path: Path | str) -> Path:
    """Export native history JSON only to a new local mode-0600 private file.

    History may contain prompts, source references, and provider/tool metadata.
    This function deliberately does not claim it has redacted those fields.
    """
    if not isinstance(run_id, str) or not run_id or not isinstance(config, OperatorConfig):
        raise ValueError("export_history requires a nonempty workflow id and v2 OperatorConfig")
    output = _private_history_path(path)
    client = await connect(config)
    history = await client.get_workflow_handle(run_id).fetch_history()
    # Include the id because WorkflowHistory.to_json intentionally omits it.
    payload = {"warning": "local private history; may contain sensitive workflow payloads; do not publish",
               "workflow_id": run_id, "history": history.to_json_dict()}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode() + b"\n"
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return output


async def replay(history: Path | str, config: OperatorConfig) -> dict[str, Any]:
    """Replay a saved native history without executing model/tool/business effects."""
    if not isinstance(config, OperatorConfig):
        raise ValueError("A v2 OperatorConfig is required")  # noqa: TRY004 - invalid admission is consistently ValueError
    path = Path(history).expanduser().absolute()
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("History must be a bounded regular local file")
    document = json.loads(path.read_text("utf-8"))
    if not isinstance(document, dict) or not isinstance(document.get("workflow_id"), str) or not isinstance(document.get("history"), dict):
        raise ValueError("History export has an invalid local wrapper")  # noqa: TRY004 - invalid admission is consistently ValueError
    # Agent construction and class assembly occur before Replayer receives the
    # workflow.  Replay supplies PydanticAIPlugin again for identical converter,
    # sandbox passthrough, and workflow failure behavior.
    workflow_class = create_workflow(config)
    parsed = WorkflowHistory.from_json(document["workflow_id"], document["history"])
    try:
        result = await Replayer(workflows=[workflow_class], plugins=[PydanticAIPlugin()],
                                workflow_failure_exception_types=[Exception]).replay_workflow(parsed)
        if result.replay_failure:
            raise result.replay_failure
    finally:
        from .agents.factory import close_agents
        await close_agents(BINDINGS[execution_identity(config)].agents)
    return {"workflow_id": parsed.workflow_id, "run_id": parsed.run_id, "replayed": True,
            "events": len(parsed.events)}


__all__ = [
    "ACTIVITY_ADMIT",
    "ACTIVITY_APPLY_REPAIR",
    "ACTIVITY_EXECUTE_REVISION",
    "ACTIVITY_FINISH",
    "ACTIVITY_FREEZE_PAIR",
    "ACTIVITY_PREPARE_STAGE",
    "ACTIVITY_RECONCILE",
    "ACTIVITY_RECORD_STAGE",
    "ACTIVITY_REVIEW_VALID",
    "ACTIVITY_REVISE_PLAN",
    "PHASE_QUERY",
    "STOP_SIGNAL",
    "WORKFLOW_NAME",
    "activity_handlers",
    "cancel",
    "create_workflow",
    "export_history",
    "replay",
    "run_worker",
    "status",
    "submit",
    "workflow_id",
]
