"""Explicit activity-boundary and worker-composition regressions."""

import inspect
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, cast

import pytest

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    DIAGNOSTIC_TRUNCATION_MARKER,
    MAX_DIAGNOSTIC_TEXT_CHARS,
    ArtifactRef,
    AuditInput,
    AuditOutput,
    Budget,
    Case,
    Disposition,
    ExecutionStatus,
    InvestigationResult,
    PreparedCase,
    ProducerInput,
    ProducerOutput,
    RunManifest,
    Submission,
)
from corsair.entrypoints import worker
from corsair.settings import Settings
from corsair.steps.activities import Activities


class InferenceStub:
    async def produce(self, request: ProducerInput) -> ProducerOutput:
        raise AssertionError(f"unexpected producer invocation: {request.run_id}")

    async def audit(self, request: AuditInput) -> AuditOutput:
        del request
        raise AssertionError("unexpected auditor invocation")


class SourcesStub:
    def prepare(self, case: Case, manifest: RunManifest) -> PreparedCase:
        del manifest
        raise AssertionError(f"unexpected source admission: {case.case_id}")

    def read_text(self, snapshot: ArtifactRef, path: str, *, max_bytes: int) -> str:
        raise AssertionError(f"unexpected source read: {snapshot.sha256} {path} {max_bytes}")

    def iter_files(self, snapshot: ArtifactRef) -> Iterable[tuple[str, bytes]]:
        raise AssertionError(f"unexpected source listing: {snapshot.sha256}")


class SandboxStub:
    @property
    def image_id(self) -> str:
        raise AssertionError("unexpected image lookup")

    def has_unknown_operation(self, operation_id: str) -> bool:
        raise AssertionError(f"unexpected operation lookup: {operation_id}")

    def execute_role(
        self,
        prepared: PreparedCase,
        submission: Submission,
        role: str,
        budget: Budget,
        heartbeat: Callable[[], None],
        *,
        operation_id: str,
    ) -> ArtifactRef:
        del prepared, submission, role, budget, heartbeat
        raise AssertionError(f"unexpected sandbox execution: {operation_id}")


def test_activities_require_all_explicit_boundary_dependencies(tmp_path: Path):
    signature = inspect.signature(Activities)
    parameters = signature.parameters
    assert tuple(parameters) == ("settings", "store", "inference", "sources", "sandbox")
    assert all(
        parameters[name].default is inspect.Parameter.empty
        for name in ("store", "inference", "sources", "sandbox")
    )
    assert all(
        parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
        for name in ("store", "inference", "sources", "sandbox")
    )

    settings = Settings(artifact_root=str(tmp_path / "artifacts"))
    store = ArtifactStore(settings.artifact_root)
    inference, sources, sandbox = InferenceStub(), SourcesStub(), SandboxStub()
    activities = Activities(
        settings,
        store=store,
        inference=inference,
        sources=sources,
        sandbox=sandbox,
    )

    assert activities.store is store
    assert activities.inference is inference
    assert activities.sources is sources
    assert activities.sandbox is sandbox
    constructor = cast(Any, Activities)
    with pytest.raises(TypeError, match="sandbox"):
        constructor(settings, store=store, inference=inference, sources=sources)


async def test_record_revalidates_model_copy_before_persistence_and_return(tmp_path: Path):
    settings = Settings(artifact_root=str(tmp_path / "artifacts"))
    store = ArtifactStore(settings.artifact_root)
    activities = Activities(
        settings,
        store=store,
        inference=InferenceStub(),
        sources=SourcesStub(),
        sandbox=SandboxStub(),
    )
    result = InvestigationResult(
        run_id="run",
        case_id="case",
        disposition=Disposition.INCONCLUSIVE,
        execution_status=ExecutionStatus.ERROR,
        reason="short failure diagnostic",
    ).model_copy(update={"reason": "x" * (MAX_DIAGNOSTIC_TEXT_CHARS * 2)})

    recorded = await activities.record(result)

    assert recorded.result_artifact is not None
    assert recorded.reason.endswith(DIAGNOSTIC_TRUNCATION_MARKER)
    persisted = InvestigationResult.model_validate(store.get_json(recorded.result_artifact))
    assert persisted.result_artifact is None
    assert persisted.reason == recorded.reason


def test_worker_composes_real_boundary_roles_around_one_store(monkeypatch, tmp_path: Path):
    created: dict[str, Any] = {}

    class StoreStub:
        def __init__(self, root: str) -> None:
            self.root = root
            created["store"] = self

    class InferenceAdapterStub:
        def __init__(self, settings: Settings, store: StoreStub) -> None:
            self.settings = settings
            self.store = store
            created["inference"] = self

    class SourcesAdapterStub:
        def __init__(self, settings: Settings, store: StoreStub) -> None:
            self.settings = settings
            self.store = store
            created["sources"] = self

    class SandboxAdapterStub:
        def __init__(self, settings: Settings, *, store: StoreStub) -> None:
            self.settings = settings
            self.store = store
            created["sandbox"] = self

    monkeypatch.setattr(worker, "ArtifactStore", StoreStub)
    monkeypatch.setattr(worker, "AdkInference", InferenceAdapterStub)
    monkeypatch.setattr(worker, "LocalSourceSnapshots", SourcesAdapterStub)
    monkeypatch.setattr(worker, "DockerSandbox", SandboxAdapterStub)

    settings = Settings(artifact_root=str(tmp_path / "worker-artifacts"))
    activities = worker.compose_worker_activities(settings)

    assert activities.store is created["store"]
    assert activities.inference is created["inference"]
    assert activities.sources is created["sources"]
    assert activities.sandbox is created["sandbox"]
    assert created["inference"].store is activities.store
    assert created["sources"].store is activities.store
    assert created["sandbox"].store is activities.store
    assert created["inference"].settings is settings
    assert created["sources"].settings is settings
    assert created["sandbox"].settings is settings


def test_worker_takes_task_slots_from_settings(monkeypatch, tmp_path: Path):
    captured: dict[str, Any] = {}

    class WorkerStub:
        def __init__(self, client: object, **options: Any) -> None:
            captured.update(options, client=client)

    monkeypatch.setattr(worker, "Worker", WorkerStub)
    settings = Settings(
        artifact_root=str(tmp_path / "artifacts"),
        task_queue="slots-queue",
        max_concurrent_activities=16,
        max_concurrent_workflow_tasks=8,
    )
    activities = Activities(
        settings,
        store=ArtifactStore(settings.artifact_root),
        inference=InferenceStub(),
        sources=SourcesStub(),
        sandbox=SandboxStub(),
    )
    client = object()

    worker.compose_worker(cast(Any, client), settings, activities)

    assert captured["client"] is client
    assert captured["task_queue"] == "slots-queue"
    assert captured["max_concurrent_activities"] == 16
    assert captured["max_concurrent_workflow_tasks"] == 8
    assert [type(item).__name__ for item in captured["interceptors"]] == [
        "LifecycleLoggingInterceptor"
    ]


def test_worker_task_slot_settings_keep_safe_defaults_and_bounds():
    defaults = Settings()
    # The default keeps the worker's historical four activity slots and the SDK's
    # default workflow-task slots; raising them is an explicit operator choice.
    assert defaults.max_concurrent_activities == 4
    assert defaults.max_concurrent_workflow_tasks == 100
    for field, value in (
        ("max_concurrent_activities", 0),
        ("max_concurrent_activities", 65),
        ("max_concurrent_workflow_tasks", 1),
        ("max_concurrent_workflow_tasks", 1001),
    ):
        with pytest.raises(ValueError, match=field):
            Settings.model_validate({field: value})
