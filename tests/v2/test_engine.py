from __future__ import annotations

import asyncio
import os
import threading
import time
from pathlib import Path

import pytest

from corsair.v2.agents import WorkspaceRef, cleanup_source_workspace
from corsair.v2.contracts import (
    Citation,
    InvestigationPlan,
    ModelProfile,
    OperatorConfig,
    ProbeSpec,
    ReportSelector,
    RunSpec,
    SandboxProfile,
    SourceRequest,
    SourceSnapshot,
    TestRecipe as NativeTestRecipe,
    Verdict,
)
from corsair.v2.engine import AdmissionError, Services, episode_input


IMAGE = "example.invalid/corsair/python@sha256:" + "c" * 64


def _local_config(tmp_path: Path) -> OperatorConfig:
    policy = tmp_path / "operator-policy.yaml"
    policy.write_bytes(b"version: test-policy\nnetwork_policies: {}\n")
    os.chmod(policy, 0o600)
    return OperatorConfig(storage_root=str(tmp_path / "store"), default_model=ModelProfile(model="test"),
                          sandbox=SandboxProfile(image=IMAGE, policy_path=str(policy), workspace_root="/workspace"))


def _local_source(tmp_path: Path) -> Path:
    source = tmp_path / "owned-source"
    source.mkdir(mode=0o700)
    (source / "app.py").write_text("def transform(value):\n    return value\n", encoding="utf-8")
    return source


def _spec(source: Path, request_id: str = "engine-request") -> RunSpec:
    return RunSpec(request_id=request_id, source=SourceRequest(path=str(source)), concern="review bounded transform",
                   language="python", framework="pytest", cwe=("CWE-20",))


def _plan() -> InvestigationPlan:
    citation = Citation(path="app.py", start_line=1, end_line=2)
    control = ProbeSpec(role="control", path="probes/control_test.py", test_id="probes/control_test.py::test_control",
                        selector=ReportSelector(name="test_control", classname="probes.control_test"),
                        objective="ordinary transform", input_description="ordinary value", expected_safe_behavior="returns value",
                        citations=(citation,))
    security = ProbeSpec(role="security", path="probes/security_test.py", test_id="probes/security_test.py::test_security",
                         selector=ReportSelector(name="test_security", classname="probes.security_test"),
                         objective="adversarial transform", input_description="hostile value", expected_safe_behavior="is rejected",
                         citations=(citation,))
    return InvestigationPlan(status="planned", summary="two independently authored native probes", target_citations=(citation,),
                             control=control, security=security,
                             recipe=NativeTestRecipe(report_format="junit", discovery_command=("discover",),
                                                     execution_command=("execute",), report_path=".corsair/report.xml"))


def _finished_verdict() -> Verdict:
    return Verdict(status="inconclusive", reason="fixture", rule_id="fixture", summary="bounded engine persistence fixture")


def test_admission_captures_owned_local_source_refuses_replay_and_returns_exact_cached_result(tmp_path: Path) -> None:
    config = _local_config(tmp_path)
    source = _local_source(tmp_path)
    spec = _spec(source)
    services = Services(config)
    try:
        admitted = services._admit(episode_input(spec, config))
        assert admitted.source_ref is not None
        captured = services.store.get_json(admitted.source_ref)
        assert captured["repository"] == str(source)
        assert [item["path"] for item in captured["files"]] == ["app.py"]
        snapshot = SourceSnapshot.model_validate(captured)
        assert services.store.get(snapshot.files[0].artifact) == b"def transform(value):\n    return value\n"

        with pytest.raises(AdmissionError, match="unfinished request"):
            services._admit(episode_input(spec, config))

        completed = services._finish(admitted, _finished_verdict(), duration_seconds=0.1)
        cached_episode = services._admit(episode_input(spec, config))
        assert cached_episode.cached_result_ref is not None
        assert services.store.get_json(cached_episode.cached_result_ref) == completed.model_dump(mode="json")
        assert services._finish(cached_episode, _finished_verdict(), duration_seconds=99.0) == completed

        changed = spec.model_copy(update={"concern": "mutated request under the same id"})
        with pytest.raises(ValueError, match="already bound to a different spec"):
            services._admit(episode_input(changed, config))
    finally:
        services.close()


def test_policy_bytes_changed_after_admission_refuse_stage_before_workspace_effect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = _local_config(tmp_path)
    services = Services(config)
    try:
        admitted = services._admit(episode_input(_spec(_local_source(tmp_path)), config))
        Path(config.sandbox.policy_path).write_bytes(b"version: mutated-policy\nnetwork_policies: {deny: all}\n")
        workspace_calls: list[object] = []

        def unexpected_workspace(*args, **kwargs):
            workspace_calls.append((args, kwargs))
            raise AssertionError("environment drift must be refused before source workspace preparation")

        monkeypatch.setattr("corsair.v2.runtime.prepare_source_workspace", unexpected_workspace)
        with pytest.raises(AdmissionError, match="changed after admission"):
            services._prepare_stage(admitted, "investigator")
        assert workspace_calls == []
    finally:
        services.close()


def test_execute_revision_cancellation_waits_for_thread_boundary_cleanup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = _local_config(tmp_path)
    services = Services(config)
    started = threading.Event()
    cleanup_done = threading.Event()
    try:
        admitted = services._admit(episode_input(_spec(_local_source(tmp_path)), config))

        def thread_boundary(episode, revision, stop_requested):
            assert revision == "baseline"
            started.set()
            deadline = time.monotonic() + 2
            while not stop_requested():
                if time.monotonic() >= deadline:
                    raise TimeoutError("cancellation did not reach the native command boundary")
                time.sleep(0.002)
            cleanup_done.set()
            return episode

        monkeypatch.setattr(services, "_execute_revision", thread_boundary)

        async def cancel() -> None:
            pending = asyncio.create_task(services.execute_revision(admitted, "baseline"))
            assert await asyncio.to_thread(started.wait, 1)
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending

        asyncio.run(cancel())
        assert cleanup_done.is_set()
    finally:
        services.close()


def test_author_stage_is_bound_to_typed_plan_and_omits_outcome_data(tmp_path: Path) -> None:
    config = _local_config(tmp_path)
    services = Services(config)
    workspace_ref: WorkspaceRef | None = None
    try:
        admitted = services._admit(episode_input(_spec(_local_source(tmp_path)), config))
        plan = _plan()
        plan_ref = services.store.put_json(plan.model_dump(mode="json"))
        episode = admitted.model_copy(update={"plan_ref": plan_ref})
        envelope = services._prepare_stage(episode, "control_author")
        workspace_ref = WorkspaceRef.model_validate(envelope.deps["workspace_ref"])
        assert envelope.public_input == {
            "concern": episode.spec.concern, "language": "python", "framework": "pytest", "cwe": ("CWE-20",),
            "probe": plan.control.model_dump(mode="json"),
        }
        assert envelope.deps["expected_probe_path"] == plan.control.path
        assert "pair" not in envelope.public_input
        assert "validity" not in envelope.public_input
        assert "expected_output" not in envelope.public_input
    finally:
        if workspace_ref is not None:
            cleanup_source_workspace(workspace_ref, config)
        services.close()
