"""Cancellation must wait for inspection setup and immutable cleanup."""

import asyncio
import threading

import pytest

from corsair.adapters.sandboxing.inspection import inspection_session


async def test_cancel_during_setup_waits_for_cleanup():
    started = threading.Event()
    release = threading.Event()
    cleaned = threading.Event()

    class Session:
        def __enter__(self):
            started.set()
            release.wait(2)
            return self

        def close(self):
            cleaned.set()

    async def run():
        async with inspection_session(Session()):
            raise AssertionError("cancelled setup must not start model")

    task = asyncio.create_task(run())
    await asyncio.to_thread(started.wait, 1)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cleaned.is_set()
