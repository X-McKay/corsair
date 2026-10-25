"""One cancellation-safe thread owner for both native CLI replay and activities."""

import asyncio
import threading
from collections.abc import Callable

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import EvidenceInput, Observation
from corsair.ports.sandboxing import SandboxPort
from corsair.settings import Settings
from corsair.steps.verification import EvidenceVerifier

Heartbeat = Callable[[], None]


async def run_evidence(
    request: EvidenceInput,
    settings: Settings,
    store: ArtifactStore,
    *,
    heartbeat: Heartbeat | None = None,
    sandbox: SandboxPort | None = None,
) -> Observation:
    cancelled = threading.Event()

    def pulse() -> None:
        if cancelled.is_set():
            raise InterruptedError("Native evidence execution cancelled")
        if heartbeat:
            heartbeat()

    task = asyncio.create_task(
        asyncio.to_thread(
            EvidenceVerifier(settings, store, sandbox).evaluate,
            request,
            pulse,
        )
    )
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        cancelled.set()
        # The native thread owns its containers, and must confirm removal before returning.
        await asyncio.gather(task, return_exceptions=True)
        raise
