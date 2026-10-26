"""Real Temporal test infrastructure with typed, offline Corsair activities."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections import Counter
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest
import pytest_asyncio
from temporalio import activity
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    AuditDecision,
    AuditInput,
    AuditOutput,
    AuditResult,
    Budget,
    Case,
    EvidenceInput,
    Finding,
    InvestigationRequest,
    InvestigationResult,
    Observation,
    PlanRevision,
    PreparedCase,
    ProducerDecision,
    ProducerInput,
    ProducerOutput,
    PythonRecipe,
    RoleObservation,
    RoleOutcome,
    RunManifest,
    Scope,
    Source,
    Submission,
    Usage,
    digest,
)
from corsair.workflows.evaluation import EvaluationWorkflow
from corsair.workflows.investigation import InvestigationWorkflow


@dataclass(frozen=True)
class ActivityScenario:
    """Deterministic outcomes for one worker's registered fake activities."""

    outcomes: tuple[tuple[RoleOutcome, RoleOutcome], ...] = (
        (RoleOutcome.HELD, RoleOutcome.VIOLATION),
    )
    # Outcomes for a later independent session (operation ids ".s<n>.r<i>");
    # None replays ``outcomes`` there too.
    later_session_outcomes: tuple[tuple[RoleOutcome, RoleOutcome], ...] | None = None
    negative_threshold: int = 2
    max_sessions: int = 2
    block_prepare: bool = False
    pause_prepare: bool = False
    pause_produce: bool = False
    fail_evidence_reason: str | None = None
    fail_fixed_evidence: bool = False
    fail_record_case_ids: frozenset[str] = frozenset()


DEFAULT_SCENARIO = ActivityScenario()


class FakeActivities:
    """Offline typed activities registered with production Temporal names.

    These activities deliberately do not emulate Docker or an LLM. They provide
    valid, source- and submission-bound trusted observations so a real worker
    executes the workflow and its deterministic policy boundary.
    """

    def __init__(self, store: ArtifactStore, scenario: ActivityScenario = DEFAULT_SCENARIO) -> None:
        self.store = store
        self.scenario = scenario
        self.call_counts: Counter[str] = Counter()
        self.producer_inputs: list[ProducerInput] = []
        self.evidence_inputs: list[EvidenceInput] = []
        self.audit_inputs: list[AuditInput] = []
        self.record_inputs: list[InvestigationResult] = []
        self.prepare_started = asyncio.Event()
        self.produce_started = asyncio.Event()
        self.produce_cancelled = asyncio.Event()
        self.prepare_completed = asyncio.Event()
        self.release_prepare = asyncio.Event()
        self.recorded = asyncio.Event()

    def _manifest(self, request: InvestigationRequest) -> RunManifest:
        return RunManifest(
            package_version="temporal-test",
            request_digest=digest(request),
            config_digest="0" * 64,
            producer_prompt_digest="1" * 64,
            auditor_prompt_digest="2" * 64,
            image_id="sha256:temporal-test",
            models={"producer": "offline", "auditor": "offline"},
            negative_threshold=self.scenario.negative_threshold,
            max_sessions=self.scenario.max_sessions,
        )

    @activity.defn(name="corsair.prepare")
    async def prepare(self, request: InvestigationRequest) -> PreparedCase:
        self.call_counts["corsair.prepare"] += 1
        self.prepare_started.set()
        if self.scenario.block_prepare:
            raise ApplicationError(
                "test source admission was blocked",
                type="PREPARE_BLOCKED",
                non_retryable=True,
            )
        source = self.store.put(
            f"admitted source for {request.case.case_id}".encode(), "application/x-tar"
        )
        fixed_source = (
            self.store.put(
                f"admitted fixed source for {request.case.case_id}".encode(),
                "application/x-tar",
            )
            if request.case.fixed_source is not None
            else None
        )
        if self.scenario.pause_prepare:
            while not self.release_prepare.is_set():
                activity.heartbeat("waiting for graceful test shutdown")
                await asyncio.sleep(0.1)
        self.prepare_completed.set()
        return PreparedCase(
            case_id=request.case.case_id,
            finding=request.case.finding,
            recipe=request.case.recipe,
            source=source,
            fixed_source=fixed_source,
            source_excerpt="4: return payload\n",
            manifest=self._manifest(request),
        )

    @activity.defn(name="corsair.produce")
    async def produce(
        self, request: ProducerInput, *, window_seconds: float | None = None
    ) -> ProducerOutput:
        self.call_counts["corsair.produce"] += 1
        self.producer_inputs.append(request)
        self.produce_started.set()
        if self.scenario.pause_produce:
            try:
                while True:
                    activity.heartbeat("waiting for test cancellation")
                    await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                self.produce_cancelled.set()
                raise
        previous_revision = request.previous.plan.revision if request.previous else None
        submission = Submission(
            control_payload="hello.txt",
            exploit_payload="../private/secret.txt",
            hypothesis="The configured target returns an attacker-controlled payload.",
            plan=PlanRevision(
                revision=request.round_index,
                parent_revision=previous_revision,
                objective="exercise the submitted control and adversarial payload pair",
                next_steps=["submit the pair to trusted evidence collection"],
                reason="the prior admissible observation did not end the investigation",
            ),
        )
        return ProducerOutput(
            decision=ProducerDecision(kind="proposal", submission=submission),
            usage=Usage(llm_calls=1, tool_calls=1),
        )

    @staticmethod
    def _role(outcome: RoleOutcome, line: int | None) -> RoleObservation:
        return RoleObservation(
            outcome=outcome,
            target_executed=True,
            covered_lines=[line or 1],
            reason="typed offline native evidence fixture",
            native_exit_code=0 if outcome is RoleOutcome.HELD else 1,
        )

    @activity.defn(name="corsair.evidence")
    async def evidence(self, request: EvidenceInput) -> Observation:
        self.call_counts["corsair.evidence"] += 1
        self.evidence_inputs.append(request)
        if self.scenario.fail_evidence_reason is not None or (
            request.fixed and self.scenario.fail_fixed_evidence
        ):
            raise ApplicationError(
                self.scenario.fail_evidence_reason or "test fixed-revision run crashed",
                type="EVIDENCE_FAILED",
                non_retryable=True,
            )
        if request.fixed:
            control, adversarial = RoleOutcome.HELD, RoleOutcome.HELD
        else:
            round_suffix = request.operation_id.rsplit(".r", 1)[-1]
            round_index = int(round_suffix) - 1 if round_suffix.isdigit() else 0
            outcomes = self.scenario.outcomes
            if ".s" in request.operation_id.removeprefix(request.run_id):
                outcomes = self.scenario.later_session_outcomes or outcomes
            control, adversarial = outcomes[min(max(round_index, 0), len(outcomes) - 1)]
        selected_source = (
            request.prepared.fixed_source if request.fixed else request.prepared.source
        )
        assert selected_source is not None
        artifact = self.store.put_json(
            {
                "schema_version": "corsair.evidence-test/1",
                "operation_id": request.operation_id,
                "source_digest": selected_source.sha256,
                "submission_digest": digest(request.submission),
                "control": control.value,
                "adversarial": adversarial.value,
            }
        )
        return Observation(
            operation_id=request.operation_id,
            source_digest=selected_source.sha256,
            submission_digest=digest(request.submission),
            control=self._role(control, request.prepared.finding.line),
            adversarial=self._role(adversarial, request.prepared.finding.line),
            cleanup_confirmed=True,
            artifact=artifact,
        )

    @activity.defn(name="corsair.audit")
    async def audit(
        self, request: AuditInput, *, window_seconds: float | None = None
    ) -> AuditOutput:
        self.call_counts["corsair.audit"] += 1
        self.audit_inputs.append(request)
        return AuditOutput(
            review=AuditResult(
                decision=AuditDecision.ACCEPT,
                rule="independent-evidence-review",
                reason="the source-bound paired observation supports the component claim",
            ),
            usage=Usage(llm_calls=1),
        )

    @activity.defn(name="corsair.record")
    async def record(self, result: InvestigationResult) -> InvestigationResult:
        self.call_counts["corsair.record"] += 1
        self.record_inputs.append(result)
        if result.case_id in self.scenario.fail_record_case_ids:
            raise ApplicationError("test result recording failed", type="RECORD_FAILED")
        from corsair.contracts import format_terminal_result

        normalized = format_terminal_result(result.model_copy(update={"result_artifact": None}))
        ref = self.store.put_json(normalized)
        self.store.commit(f"result.{result.run_id}", ref)
        self.recorded.set()
        return format_terminal_result(normalized.model_copy(update={"result_artifact": ref}))

    def registered(self) -> list:
        return [self.prepare, self.produce, self.evidence, self.audit, self.record]


@dataclass(frozen=True)
class TemporalServer:
    """A client plus a factory for short-lived workers on unique queues."""

    client: Client

    @asynccontextmanager
    async def worker(
        self,
        store: ArtifactStore,
        scenario: ActivityScenario = DEFAULT_SCENARIO,
        *,
        task_queue: str | None = None,
    ) -> AsyncGenerator[tuple[str, FakeActivities]]:
        activities = FakeActivities(store, scenario)
        task_queue = task_queue or temporal_id("queue")
        async with Worker(
            self.client,
            task_queue=task_queue,
            workflows=[InvestigationWorkflow, EvaluationWorkflow],
            activities=activities.registered(),
            max_concurrent_activities=8,
        ):
            yield task_queue, activities


def temporal_id(label: str) -> str:
    """Return a unique legal Temporal workflow or task-queue identifier under 60 chars."""

    return f"temporal-{label}-{uuid.uuid4().hex[:20]}"


def investigation_request(
    case_id: str = "case",
    *,
    fixed: bool = False,
    budget: Budget | None = None,
) -> InvestigationRequest:
    """Create a fully typed input whose source path is never read by fake activities."""

    return InvestigationRequest(
        case=Case(
            case_id=case_id,
            finding=Finding(
                title="payload disclosure",
                description="The configured component may return an untrusted payload.",
                file="reader.py",
                line=4,
                claim_scope=Scope.COMPONENT,
            ),
            source=Source(path="admitted"),
            fixed_source=Source(path="fixed") if fixed else None,
            recipe=PythonRecipe(
                module_file="reader.py",
                function="read_payload",
                payload_parameter="path",
                fixed_kwargs={"root": "/fixtures"},
            ),
        ),
        budget=budget
        or Budget(
            max_rounds=1,
            max_llm_calls=2,
            episode_llm_calls=1,
            max_tool_calls=1,
            max_output_tokens=256,
            max_elapsed_seconds=30,
            probe_timeout_seconds=1,
        ),
    )


@pytest.fixture
def temporal_artifact_store(tmp_path: Path) -> ArtifactStore:
    """Each test gets an actual immutable artifact store, including final result records."""

    return ArtifactStore(tmp_path / "temporal-artifacts")


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def temporal_server() -> AsyncGenerator[TemporalServer]:
    """Start and stop a real server unless CI supplies an existing address.

    The explicit opt-in avoids downloading or launching the Temporal CLI during
    ordinary unit-test runs. Once enabled, connection or server startup failures
    are deliberately propagated as test failures.
    """

    if os.environ.get("CORSAIR_TEST_TEMPORAL") != "1":
        pytest.skip("set CORSAIR_TEST_TEMPORAL=1 to run Temporal server tests")
    address = os.environ.get("CORSAIR_TEMPORAL_ADDRESS")
    if address:
        client = await Client.connect(address, data_converter=pydantic_data_converter)
        yield TemporalServer(client)
        return
    cache = Path.home() / ".cache" / "corsair-temporal"
    cache.mkdir(parents=True, exist_ok=True)
    environment = await WorkflowEnvironment.start_local(
        data_converter=pydantic_data_converter,
        download_dest_dir=str(cache),
        dev_server_log_level="error",
    )
    try:
        yield TemporalServer(environment.client)
    finally:
        await environment.shutdown()


__all__: Sequence[str] = (
    "ActivityScenario",
    "FakeActivities",
    "TemporalServer",
    "investigation_request",
    "temporal_artifact_store",
    "temporal_id",
    "temporal_server",
)
