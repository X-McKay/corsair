"""One cancellation-safe thread owner for both native CLI replay and activities."""

import asyncio
import threading

from corsair.contracts import EvidenceInput
from corsair.runtime.artifacts import ArtifactStore
from corsair.settings import Settings
from corsair.tools.security.evidence import EvidenceVerifier


async def run_evidence(
    request: EvidenceInput,
    settings: Settings,
    store: ArtifactStore,
    *,
    heartbeat=None,
    sandbox=None,
):
    cancelled = threading.Event()

    def pulse():
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
