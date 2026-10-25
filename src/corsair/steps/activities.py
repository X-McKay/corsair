"""The only nondeterministic boundary used by the workflows."""

import asyncio

from temporalio import activity
from temporalio.exceptions import ApplicationError

from corsair.adapters.storage.filesystem import ArtifactStore
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
from corsair.ports.inference import InferencePort
from corsair.ports.sandboxing import SandboxPort
from corsair.ports.scm import SourceSnapshotPort
from corsair.settings import Settings
from corsair.steps.manifest import build_manifest


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

    @activity.defn(name="corsair.prepare")
    async def prepare(self, request: InvestigationRequest) -> PreparedCase:
        activity.heartbeat("preparing")
        try:
            image_id = await asyncio.to_thread(lambda: self.sandbox.image_id)
        except Exception as exc:
            raise ApplicationError(
                "Docker daemon or the pinned Corsair image is unavailable",
                type="PREPARE_BLOCKED",
                non_retryable=True,
            ) from exc
        manifest = build_manifest(request, self.settings, image_id)
        try:
            return await asyncio.to_thread(self.sources.prepare, request.case, manifest)
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
        return await self._model_episode(self.inference.produce(request))

    @activity.defn(name="corsair.audit")
    async def audit(self, request: AuditInput) -> AuditOutput:
        return await self._model_episode(self.inference.audit(request))

    @activity.defn(name="corsair.evidence")
    async def evidence(self, request: EvidenceInput) -> Observation:
        from corsair.steps.evidence import run_evidence

        loop = asyncio.get_running_loop()

        def heartbeat():
            if activity.is_cancelled():
                raise InterruptedError("Evidence activity cancelled")
            loop.call_soon_threadsafe(activity.heartbeat, request.operation_id)

        return await run_evidence(
            request, self.settings, self.store, heartbeat=heartbeat, sandbox=self.sandbox
        )

    @activity.defn(name="corsair.record")
    async def record(self, result: InvestigationResult) -> InvestigationResult:
        normalized = result.model_copy(update={"result_artifact": None})
        ref = await asyncio.to_thread(self.store.put_json, normalized)
        await asyncio.to_thread(self.store.commit, f"result.{result.run_id}", ref)
        return result.model_copy(update={"result_artifact": ref})

    def registered(self) -> list:
        return [self.prepare, self.produce, self.evidence, self.audit, self.record]
