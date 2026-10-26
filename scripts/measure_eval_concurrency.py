#!/usr/bin/env python3
"""Measure evaluation-batch wall time against batch and worker concurrency.

A real local Temporal test server (started here; never an existing address), the
production worker composition (``compose_worker``), the real ``Activities``, source
admission, evidence verifier and workflows run one N-case batch per grid point. Only
the two external ports are doubles: an inference port whose producer and auditor
episodes each sleep a fixed time, and a sandbox whose control and adversarial roles
each sleep a fixed time and return a well-formed raw receipt. No model is called and
no target code runs, so the numbers measure coordination and slot limits, not model
or container cost.

Run from the repository root inside the Nix shell::

    uv run --locked python scripts/measure_eval_concurrency.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from temporalio import activity
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment

from corsair.adapters.scm.local import LocalSourceSnapshots
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    ArtifactRef,
    AuditDecision,
    AuditInput,
    AuditOutput,
    AuditResult,
    BatchRequest,
    Budget,
    InvestigationRequest,
    InvestigationResult,
    PlanRevision,
    PreparedCase,
    ProducerDecision,
    ProducerInput,
    ProducerOutput,
    Submission,
    Usage,
    digest,
)
from corsair.entrypoints.api import start_evaluation
from corsair.entrypoints.requests import load_investigation_request
from corsair.entrypoints.worker import compose_worker
from corsair.ports.sandboxing import SandboxRole
from corsair.settings import Settings
from corsair.steps.activities import Activities

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "evals/fixtures/case01/request.json"
IMAGE_ID = "sha256:measure-eval-concurrency"


@dataclass
class Probe:
    """Thread-safe in-flight and task-queue wait accounting across the fake ports."""

    lock: threading.Lock = field(default_factory=threading.Lock)
    in_flight: dict[str, int] = field(default_factory=lambda: {"model": 0, "container": 0})
    peaks: dict[str, int] = field(default_factory=lambda: {"model": 0, "container": 0, "all": 0})
    waits: dict[str, list[float]] = field(default_factory=dict)

    def enter(self, kind: str) -> None:
        with self.lock:
            self.in_flight[kind] += 1
            self.peaks[kind] = max(self.peaks[kind], self.in_flight[kind])
            self.peaks["all"] = max(self.peaks["all"], sum(self.in_flight.values()))

    def exit(self, kind: str) -> None:
        with self.lock:
            self.in_flight[kind] -= 1

    def queued(self, name: str) -> None:
        """Record how long the current activity attempt waited for a worker slot."""
        info = activity.info()
        waited = (datetime.now(UTC) - info.current_attempt_scheduled_time).total_seconds()
        with self.lock:
            self.waits.setdefault(name, []).append(max(0.0, waited))


@dataclass
class SleepingInference:
    """An inference port whose episodes take a fixed time and propose one fixed pair."""

    seconds: float
    probe: Probe

    async def _episode(self, name: str) -> None:
        self.probe.queued(name)
        self.probe.enter("model")
        try:
            await asyncio.sleep(self.seconds)
        finally:
            self.probe.exit("model")

    async def produce(
        self, request: ProducerInput, *, window_seconds: float | None = None
    ) -> ProducerOutput:
        del window_seconds
        await self._episode("produce")
        previous = request.previous.plan.revision if request.previous else None
        submission = Submission(
            control_payload="hello.txt",
            exploit_payload="../private/secret.txt",
            hypothesis="Caller-controlled path joins the root without containment.",
            plan=PlanRevision(
                revision=request.round_index,
                parent_revision=previous,
                objective="Exercise the reported component file-access boundary",
                next_steps=["Submit benign and path-traversal payloads"],
                reason="The reported callable is the production seam",
            ),
        )
        return ProducerOutput(
            decision=ProducerDecision(kind="proposal", submission=submission),
            usage=Usage(llm_calls=1, tool_calls=1),
        )

    async def audit(
        self, request: AuditInput, *, window_seconds: float | None = None
    ) -> AuditOutput:
        del window_seconds
        del request  # Fixed acceptance; the measurement does not exercise audit content.
        await self._episode("audit")
        return AuditOutput(
            review=AuditResult(
                decision=AuditDecision.ACCEPT,
                rule="measurement-fixture",
                reason="The paired payloads exercise the configured file-access seam",
            ),
            usage=Usage(llm_calls=1),
        )


@dataclass
class SleepingSandbox:
    """A sandbox port whose roles take a fixed time and return a valid raw receipt.

    The vulnerable revision violates on the adversarial role; the fixed revision holds
    on both, so the batch reaches the same SUPPORTED/verified path as the chain test.
    """

    store: ArtifactStore
    seconds: float
    probe: Probe

    @property
    def image_id(self) -> str:
        return IMAGE_ID

    def has_unknown_operation(self, operation_id: str) -> bool:
        del operation_id  # Every measurement operation id is fresh.
        return False

    def execute_role(
        self,
        prepared: PreparedCase,
        submission: Submission,
        role: SandboxRole,
        budget: Budget,
        heartbeat: Callable[[], None],
        *,
        operation_id: str,
    ) -> ArtifactRef:
        del budget  # The fixed sleep stands in for the probe deadline.
        if role == "control":
            self.probe.queued("evidence")
        heartbeat()
        self.probe.enter("container")
        try:
            time.sleep(self.seconds)
        finally:
            self.probe.exit("container")
        violation = role == "adversarial" and prepared.fixed_source is not None
        driver = {
            "schema_version": "corsair.driver/1",
            "operation_id": operation_id,
            "role": role,
            "source_digest": prepared.source.sha256,
            "submission_digest": digest(submission),
            "native_exit_code": 1 if violation else 0,
            "junit": {
                "status": "FAILURE" if violation else "PASS",
                "tests": 1,
                "failures": 1 if violation else 0,
                "errors": 0,
                "skipped": 0,
            },
            "outcome": "VIOLATION" if violation else "PROPERTY_HELD",
            "observation_kind": "disclosure" if violation else "held",
            "target_executed": True,
            "covered_lines": [prepared.finding.line or 1],
            "coverage_file": prepared.recipe.module_file,
        }
        return self.store.put_json(
            {
                "schema_version": "corsair.raw-evidence/1",
                "operation_id": operation_id,
                "role": role,
                "container_id": f"measure-{operation_id}-{role}",
                "labels": {
                    "corsair.security": "true",
                    "corsair.operation": operation_id,
                    "corsair.role": role,
                },
                "cleanup_confirmed": True,
                "docker_exit_code": 1 if violation else 0,
                "image_id": IMAGE_ID,
                "driver": driver,
            }
        )


@dataclass(frozen=True)
class Measurement:
    cases: int
    concurrency: int
    slots: int
    wall_seconds: float
    peak_model: int
    peak_container: int
    peak_in_flight: int
    max_queue_wait_seconds: dict[str, float]
    dispositions: dict[str, int]


def batch_requests(cases: int) -> list[InvestigationRequest]:
    """N distinct case identities over the frozen case01 request (source never changes)."""
    request = load_investigation_request(CASE)
    return [
        request.model_copy(
            update={"case": request.case.model_copy(update={"case_id": f"case01-m{index}"})}
        )
        for index in range(cases)
    ]


async def measure(
    client: Client,
    work: Path,
    *,
    cases: int,
    concurrency: int,
    slots: int,
    episode_seconds: float,
    role_seconds: float,
    workflow_tasks: int = 100,
) -> Measurement:
    """Run one batch through a fresh production-composed worker and time it end to end."""
    label = uuid.uuid4().hex[:12]
    settings = Settings(
        source_root=str(ROOT),
        artifact_root=str(work / f"artifacts-{label}"),
        task_queue=f"measure-{label}",
        max_concurrent_activities=slots,
        max_concurrent_workflow_tasks=workflow_tasks,
    )
    store = ArtifactStore(settings.artifact_root)
    probe = Probe()
    activities = Activities(
        settings,
        store=store,
        inference=SleepingInference(episode_seconds, probe),
        sources=LocalSourceSnapshots(settings, store),
        sandbox=SleepingSandbox(store, role_seconds, probe),
    )
    batch = BatchRequest(
        batch_id=f"measure-batch-{label}",
        requests=batch_requests(cases),
        concurrency=concurrency,
    )
    async with compose_worker(client, settings, activities):
        started = time.perf_counter()
        handle = await start_evaluation(client, batch, settings)
        items = await handle.result()
        wall = time.perf_counter() - started
    dispositions: dict[str, int] = {}
    for item in items:
        if item.artifact is None:
            key = "error"
        else:
            result = InvestigationResult.model_validate(store.get_json(item.artifact))
            key = result.disposition.value
        dispositions[key] = dispositions.get(key, 0) + 1
    return Measurement(
        cases=cases,
        concurrency=concurrency,
        slots=slots,
        wall_seconds=round(wall, 2),
        peak_model=probe.peaks["model"],
        peak_container=probe.peaks["container"],
        peak_in_flight=probe.peaks["all"],
        max_queue_wait_seconds={
            name: round(max(values), 2) for name, values in sorted(probe.waits.items())
        },
        dispositions=dispositions,
    )


def table(rows: list[Measurement]) -> str:
    """Render a Markdown scaling table; speedup is against concurrency 1 at equal slots."""
    baseline = {row.slots: row.wall_seconds for row in rows if row.concurrency == 1}
    lines = [
        "| slots | --concurrency | wall s | speedup | peak in flight | max queue wait s |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        base = baseline.get(row.slots)
        speedup = f"{base / row.wall_seconds:.2f}x" if base else "-"
        wait = max(row.max_queue_wait_seconds.values(), default=0.0)
        lines.append(
            f"| {row.slots} | {row.concurrency} | {row.wall_seconds:.1f} | {speedup} "
            f"| {row.peak_in_flight} | {wait:.2f} |"
        )
    return "\n".join(lines)


async def run(args: argparse.Namespace) -> list[Measurement]:
    cache = Path.home() / ".cache" / "corsair-temporal"
    cache.mkdir(parents=True, exist_ok=True)
    environment = await WorkflowEnvironment.start_local(
        data_converter=pydantic_data_converter,
        download_dest_dir=str(cache),
        dev_server_log_level="error",
    )
    rows: list[Measurement] = []
    try:
        with tempfile.TemporaryDirectory(prefix="corsair-measure-") as work:
            for slots in args.slots:
                for concurrency in args.concurrency:
                    row = await measure(
                        environment.client,
                        Path(work),
                        cases=args.cases,
                        concurrency=concurrency,
                        slots=slots,
                        episode_seconds=args.episode_seconds,
                        role_seconds=args.role_seconds,
                    )
                    print(json.dumps(asdict(row)), flush=True)
                    rows.append(row)
    finally:
        await environment.shutdown()
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cases", type=int, default=8)
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 2, 4, 8])
    parser.add_argument("--slots", type=int, nargs="+", default=[4, 16])
    parser.add_argument("--episode-seconds", type=float, default=2.0)
    parser.add_argument("--role-seconds", type=float, default=0.5)
    rows = asyncio.run(run(parser.parse_args()))
    print(table(rows))


if __name__ == "__main__":
    main()
