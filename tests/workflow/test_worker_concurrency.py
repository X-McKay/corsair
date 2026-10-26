"""Worker activity slots, not a batch's --concurrency alone, bound evaluation throughput.

The production worker composition and real activities run against the real local
Temporal test server; only the inference and sandbox ports are timed doubles from
scripts/benchmarks/measure_eval_concurrency.py, so no model or container runs.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
MEASURE_SCRIPT = ROOT / "scripts/benchmarks/measure_eval_concurrency.py"


def _measure_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("measure_eval_concurrency", MEASURE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="module")
async def test_worker_activity_slots_bound_concurrent_child_investigations(
    temporal_server, tmp_path: Path
):
    measure = _measure_module()

    async def batch(slots: int, workflow_tasks: int):
        return await measure.measure(
            temporal_server.client,
            tmp_path,
            cases=4,
            concurrency=4,
            slots=slots,
            workflow_tasks=workflow_tasks,
            episode_seconds=0.5,
            role_seconds=0.05,
        )

    # Two activity slots (and the SDK's minimum of two workflow-task slots) still
    # complete the whole batch, but only two investigations progress at once and the
    # rest wait in the task queue for at least one episode.
    capped = await batch(slots=2, workflow_tasks=2)
    assert capped.dispositions == {"SUPPORTED": 4}
    assert capped.peak_in_flight == 2
    assert max(capped.max_queue_wait_seconds.values()) >= 0.4

    # Slots at the batch's --concurrency let every child run at once without queueing
    # behind another child's episode.
    sized = await batch(slots=4, workflow_tasks=100)
    assert sized.dispositions == {"SUPPORTED": 4}
    assert sized.peak_in_flight == 4
    assert max(sized.max_queue_wait_seconds.values()) < 0.4
