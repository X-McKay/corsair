"""The only nondeterministic boundary used by the workflows."""

import asyncio
import threading

from temporalio import activity
from temporalio.exceptions import ApplicationError

from corsair.contracts import (
    AuditInput,
    AuditOutput,
    EvidenceInput,
    InvestigationRequest,
    InvestigationResult,
    Observation,
    PreparedCase,
    ProducerInput,
    ProducerOutput,
)
from corsair.runtime.artifacts import ArtifactStore
from corsair.runtime.manifest import build_manifest
from corsair.settings import Settings


class Activities:
    def __init__(self, settings: Settings, *, model_override=None):
        self.settings = settings
        self.store = ArtifactStore(settings.artifact_root)
        self.model_override = model_override

    @activity.defn(name="corsair.prepare")
    async def prepare(self, request: InvestigationRequest) -> PreparedCase:
        from corsair.tools.security.sandbox import DockerSandbox
        from corsair.tools.security.sources import prepare_case

        activity.heartbeat("preparing")
        try:
            image_id = await asyncio.to_thread(lambda: DockerSandbox(self.settings).image_id)
        except Exception as exc:
            raise ApplicationError(
                "Docker daemon or the pinned Corsair image is unavailable",
                type="PREPARE_BLOCKED",
                non_retryable=True,
            ) from exc
        manifest = build_manifest(request, self.settings, image_id)
        try:
            return await asyncio.to_thread(
                prepare_case, request.case, self.settings, self.store, manifest
            )
        except (ValueError, FileNotFoundError, PermissionError) as exc:
            raise ApplicationError(str(exc), type="SOURCE_DENIED", non_retryable=True) from exc

    async def _model_episode(self, awaitable):
        async def heartbeats():
            while True:
                activity.heartbeat("agent episode")
                await asyncio.sleep(2)

        heartbeat_task = asyncio.create_task(heartbeats())
        try:
            return await awaitable
        finally:
            heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)

    @activity.defn(name="corsair.produce")
    async def produce(self, request: ProducerInput) -> ProducerOutput:
        from corsair.runtime.agent_runner import run_producer

        return await self._model_episode(
            run_producer(request, self.settings, self.store, model_override=self.model_override)
        )

    @activity.defn(name="corsair.audit")
    async def audit(self, request: AuditInput) -> AuditOutput:
        from corsair.runtime.agent_runner import run_auditor

        return await self._model_episode(
            run_auditor(request, self.settings, model_override=self.model_override)
        )

    @activity.defn(name="corsair.evidence")
    async def evidence(self, request: EvidenceInput) -> Observation:
        from corsair.tools.security.evidence import EvidenceVerifier

        cancelled = threading.Event()
        loop = asyncio.get_running_loop()

        def heartbeat():
            if cancelled.is_set() or activity.is_cancelled():
                raise InterruptedError("Evidence activity cancelled")
            loop.call_soon_threadsafe(activity.heartbeat, request.operation_id)

        task = asyncio.create_task(
            asyncio.to_thread(
                EvidenceVerifier(self.settings, self.store).evaluate, request, heartbeat
            )
        )
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled.set()
            # The thread owns its container; it must clean up before cancellation completes.
            await asyncio.gather(task, return_exceptions=True)
            raise

    @activity.defn(name="corsair.record")
    async def record(self, result: InvestigationResult) -> InvestigationResult:
        normalized = result.model_copy(update={"result_artifact": None})
        ref = await asyncio.to_thread(self.store.put_json, normalized)
        await asyncio.to_thread(self.store.commit, f"result.{result.run_id}", ref)
        return result.model_copy(update={"result_artifact": ref})

    def registered(self) -> list:
        return [self.prepare, self.produce, self.evidence, self.audit, self.record]
