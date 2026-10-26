"""The only nondeterministic boundary used by the workflows."""

import asyncio

from temporalio import activity
from temporalio.exceptions import ApplicationError

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    MAX_TERMINAL_ROUNDS,
    AuditInput,
    AuditOutput,
    EvidenceInput,
    InvestigationRequest,
    InvestigationResult,
    Observation,
    PreparedCase,
    ProducerInput,
    ProducerOutput,
    format_diagnostic,
    format_terminal_result,
)
from corsair.policies.target_binding import TargetBindingBlocked
from corsair.policies.time_bounds import activity_window_seconds
from corsair.ports.inference import InferencePort
from corsair.ports.sandboxing import SandboxPort
from corsair.ports.scm import SourceSnapshotPort
from corsair.settings import Settings
from corsair.steps.manifest import build_manifest

# Seconds between heartbeats while an activity awaits blocking work. Well inside every
# heartbeat timeout the workflow schedules (heartbeat_seconds), so a slow Docker daemon,
# source admission or model episode is never mistaken for a lost worker.
HEARTBEAT_INTERVAL_SECONDS = 2.0


class Activities:
    def __init__(
        self,
        settings: Settings,
        *,
        store: ArtifactStore,
        inference: InferencePort,
        sources: SourceSnapshotPort,
        sandbox: SandboxPort,
    ):
        self.settings = settings
        self.store = store
        self.inference = inference
        self.sources = sources
        self.sandbox = sandbox

    @staticmethod
    def _activity_error(
        error: Exception, error_type: str, *, non_retryable: bool
    ) -> ApplicationError:
        """Bound transport diagnostics; the original exception chain must not defeat the cap."""
        return ApplicationError(
            format_diagnostic(f"{type(error).__name__}: {error}"),
            type=error_type,
            non_retryable=non_retryable,
        )

    @activity.defn(name="corsair.prepare")
    async def prepare(self, request: InvestigationRequest) -> PreparedCase:
        kind = request.case.recipe.kind
        try:
            image_id = await self._with_heartbeats(
                asyncio.to_thread(self.sandbox.image_id_for, kind), "preparing"
            )
        except Exception as exc:
            raise ApplicationError(
                "Docker daemon or the pinned Corsair image is unavailable",
                type="PREPARE_BLOCKED",
                non_retryable=True,
            ) from exc
        manifest = build_manifest(request, self.settings, image_id)
        if request.budget.max_rounds * manifest.max_sessions > MAX_TERMINAL_ROUNDS:
            raise ApplicationError(
                f"max_rounds {request.budget.max_rounds} x max_sessions {manifest.max_sessions} "
                f"exceeds the {MAX_TERMINAL_ROUNDS}-round terminal result capacity",
                type="PREPARE_BLOCKED",
                non_retryable=True,
            )
        try:
            # Preparation also binds the target, over the admitted bytes: a case that
            # certainly cannot bind stops here as UNABLE_TO_RUN, before any model or
            # container cost (Python callable recipes; see prepare_case).
            return await self._with_heartbeats(
                asyncio.to_thread(self.sources.prepare, request.case, manifest), "preparing"
            )
        except TargetBindingBlocked as exc:
            raise ApplicationError(
                format_diagnostic(str(exc)), type="PREPARE_BLOCKED", non_retryable=True
            ) from None
        except (ValueError, FileNotFoundError, PermissionError) as exc:
            raise self._activity_error(exc, "SOURCE_DENIED", non_retryable=True) from None

    @staticmethod
    def _activity_window() -> float | None:
        """Time left to this activity attempt, from the bounds the workflow scheduled."""
        info = activity.info()
        queued = (info.started_time - info.current_attempt_scheduled_time).total_seconds()
        start_to_close, schedule_to_close = (
            info.start_to_close_timeout,
            info.schedule_to_close_timeout,
        )
        return activity_window_seconds(
            start_to_close.total_seconds() if start_to_close else None,
            schedule_to_close.total_seconds() if schedule_to_close else None,
            queued,
        )

    @staticmethod
    async def _with_heartbeats(awaitable, detail: str):
        """Await ``awaitable`` while heartbeating ``detail`` every interval until it ends."""

        async def heartbeats():
            while True:
                activity.heartbeat(detail)
                await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)

        heartbeat_task = asyncio.create_task(heartbeats())
        try:
            return await awaitable
        finally:
            heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)

    @activity.defn(name="corsair.produce")
    async def produce(self, request: ProducerInput) -> ProducerOutput:
        try:
            window = self._activity_window()
            return await self._with_heartbeats(
                self.inference.produce(request, window_seconds=window), "agent episode"
            )
        except Exception as exc:
            raise self._activity_error(exc, "PRODUCER_FAILED", non_retryable=True) from None

    @activity.defn(name="corsair.audit")
    async def audit(self, request: AuditInput) -> AuditOutput:
        try:
            window = self._activity_window()
            return await self._with_heartbeats(
                self.inference.audit(request, window_seconds=window), "agent episode"
            )
        except Exception as exc:
            raise self._activity_error(exc, "AUDITOR_FAILED", non_retryable=True) from None

    @activity.defn(name="corsair.evidence")
    async def evidence(self, request: EvidenceInput) -> Observation:
        from corsair.steps.evidence import run_evidence

        loop = asyncio.get_running_loop()

        def heartbeat():
            if activity.is_cancelled():
                raise InterruptedError("Evidence activity cancelled")
            loop.call_soon_threadsafe(activity.heartbeat, request.operation_id)

        try:
            return await run_evidence(
                request, self.settings, self.store, heartbeat=heartbeat, sandbox=self.sandbox
            )
        except Exception as exc:
            raise self._activity_error(exc, "EVIDENCE_FAILED", non_retryable=True) from None

    @activity.defn(name="corsair.record")
    async def record(self, result: InvestigationResult) -> InvestigationResult:
        try:
            normalized = format_terminal_result(result.model_copy(update={"result_artifact": None}))
        except ValueError as exc:
            raise self._activity_error(exc, "RECORD_PAYLOAD_INVALID", non_retryable=True) from None
        try:
            ref = await asyncio.to_thread(self.store.put_json, normalized)
            await asyncio.to_thread(self.store.commit, f"result.{normalized.run_id}", ref)
        except Exception as exc:
            raise self._activity_error(exc, "RECORD_FAILED", non_retryable=False) from None
        try:
            return format_terminal_result(normalized.model_copy(update={"result_artifact": ref}))
        except ValueError as exc:
            raise self._activity_error(exc, "RECORD_PAYLOAD_INVALID", non_retryable=True) from None

    def registered(self) -> list:
        return [self.prepare, self.produce, self.evidence, self.audit, self.record]
