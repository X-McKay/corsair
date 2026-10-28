from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    ArtifactRef,
    AuditDecision,
    AuditOutput,
    AuditResult,
    AuditRule,
    Budget,
    Disposition,
    EvidenceInput,
    ExecutionStatus,
    Finding,
    FixStatus,
    KernelCase,
    Observation,
    PlanRevision,
    PreparedCase,
    PythonRecipe,
    RoleObservation,
    RoleOutcome,
    RoundResult,
    RunManifest,
    Scope,
    Submission,
    Verdict,
    digest,
)
from corsair.contracts.evidence import ErrorKind
from corsair.policies.verdicts import decide, fix_status, session_verdict
from corsair.ports.sandboxing import SandboxUnavailable
from corsair.settings import Settings
from corsair.steps.verification import EvidenceVerifier

SOURCE_DIGEST = "a" * 64
ARTIFACT_DIGEST = "d" * 64


def _prepared() -> PreparedCase:
    from corsair.contracts import ArtifactRef

    return PreparedCase(
        case_id="case",
        finding=Finding(
            title="secret path",
            description="component finding",
            file="reader.py",
            line=4,
            claim_scope=Scope.COMPONENT,
        ),
        recipe=PythonRecipe(
            module_file="reader.py",
            function="read_file",
            payload_parameter="path",
            fixed_kwargs={"root": "/fixtures/allowed"},
        ),
        source=ArtifactRef(sha256=SOURCE_DIGEST, size=1, media_type="application/x-tar"),
        source_excerpt="4: return read(path)",
        manifest=RunManifest(
            package_version="0.1",
            request_digest="1" * 64,
            config_digest="2" * 64,
            producer_prompt_digest="3" * 64,
            auditor_prompt_digest="4" * 64,
            image_id="sha256:trusted",
            models={"producer": "test", "auditor": "test"},
        ),
    )


def _submission() -> Submission:
    return Submission(
        control_payload="hello.txt",
        exploit_payload="../private/secret.txt",
        hypothesis="read path traversal",
        plan=PlanRevision(
            revision=1,
            objective="verify",
            next_steps=["probe"],
            reason="operator-owned recipe",
        ),
    )


@dataclass
class _FakeSandbox:
    store: ArtifactStore
    forged: bool = False
    unknown: bool = False
    cleanup_confirmed: bool = True
    calls: int = 0
    image_id: str = "sha256:trusted"
    raw_image_id: object = "sha256:trusted"
    omit_raw_image_id: bool = False
    adversarial_violates: bool = True
    # Sandbox timing: the trusted adapter's host_usec and the driver's wall/cpu usec.
    # None leaves a field out of the receipt, as every receipt saved before it existed.
    host_usec: object = None
    wall_usec: object = None
    cpu_usec: object = None
    # A native ERROR adversarial record: its observation kind, covered lines and coverage
    # file, as a driver writes them (target_executed is false for every ERROR kind).
    adversarial_error: bool = False
    error_kind: object = "execution_error"
    error_lines: tuple[int, ...] = (4,)
    error_coverage_file: str | None = None
    # A receipt with no driver record and the adapter's error string for this role.
    receipt_error: str | None = None
    raises: dict[str, Exception] | None = None

    def image_id_for(self, kind: str) -> str:
        del kind  # The double resolves one trusted image regardless of recipe kind.
        return self.image_id

    def has_unknown_operation(self, operation_id: str) -> bool:
        del operation_id  # Test-controlled operation state, independent of its identity.
        return self.unknown

    def execute_role(self, prepared, submission, role, budget, heartbeat, *, operation_id):
        store = self.store
        del budget, heartbeat
        self.calls += 1
        if self.raises and role in self.raises:
            raise self.raises[role]
        violation = role == "adversarial" and self.adversarial_violates
        driver = {
            "schema_version": "corsair.driver/1",
            "operation_id": operation_id,
            "role": role,
            "source_digest": "b" * 64 if self.forged else prepared.source.sha256,
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
            "covered_lines": [4],
            "coverage_file": prepared.recipe.module_file,
        }
        if role == "adversarial" and self.adversarial_error:
            driver.update(
                native_exit_code=1,
                junit={"status": "ERROR", "tests": 1, "failures": 0, "errors": 1, "skipped": 0},
                outcome="ERROR",
                observation_kind=self.error_kind,
                target_executed=False,
                covered_lines=list(self.error_lines),
                coverage_file=self.error_coverage_file or prepared.recipe.module_file,
            )
        for key, value in (("wall_usec", self.wall_usec), ("cpu_usec", self.cpu_usec)):
            if value is not None:
                driver[key] = value
        raw = {
            "schema_version": "corsair.raw-evidence/1",
            "operation_id": operation_id,
            "role": role,
            "container_id": f"id-{role}",
            "labels": {
                "corsair.security": "true",
                "corsair.operation": operation_id,
                "corsair.role": role,
            },
            "cleanup_confirmed": self.cleanup_confirmed,
            "docker_exit_code": driver["native_exit_code"],
            "driver": driver,
        }
        if role == "adversarial" and self.receipt_error is not None:
            raw.update(driver=None, error=self.receipt_error, docker_exit_code=2)
        if not self.omit_raw_image_id:
            raw["image_id"] = self.raw_image_id
        if self.host_usec is not None:
            raw["host_usec"] = self.host_usec
        ref = store.put_json(raw)
        return ref


def _input(operation_id: str = "operation") -> EvidenceInput:
    return EvidenceInput(
        run_id="run",
        operation_id=operation_id,
        prepared=_prepared(),
        submission=_submission(),
        budget=Budget(probe_timeout_seconds=5),
    )


def _audit(decision: AuditDecision = AuditDecision.ACCEPT) -> AuditOutput:
    rule = AuditRule.ALL if decision is AuditDecision.ACCEPT else AuditRule.R1
    return AuditOutput(review=AuditResult(decision=decision, rule=rule, reason="reviewed"))


def test_evidence_reconciles_committed_result_without_rerunning(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    sandbox = _FakeSandbox(store)
    verifier = EvidenceVerifier(Settings(), store, sandbox)

    first = verifier.evaluate(_input())
    second = verifier.evaluate(_input())

    assert first == second
    assert sandbox.calls == 2
    assert first.cleanup_confirmed is True
    assert first.control and first.control.outcome is RoleOutcome.HELD
    assert first.adversarial and first.adversarial.outcome is RoleOutcome.VIOLATION
    assert first.artifact is not None


def test_unconfirmed_control_cleanup_preserves_receipt_and_skips_adversarial(
    tmp_path: Path,
) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    sandbox = _FakeSandbox(store, cleanup_confirmed=False)
    observation = EvidenceVerifier(Settings(), store, sandbox).evaluate(_input())

    assert sandbox.calls == 1
    assert observation.control and observation.control.outcome is RoleOutcome.INVALID
    assert observation.adversarial == RoleObservation(
        outcome=RoleOutcome.ERROR,
        target_executed=False,
        reason="role was not executed",
        error_kind="sandbox",
    )
    assert observation.cleanup_confirmed is False
    assert observation.artifact is not None
    bundle = store.get_json(observation.artifact)
    control_raw = ArtifactRef.model_validate(bundle["roles"]["control"])
    assert store.get_json(control_raw)["cleanup_confirmed"] is False
    assert bundle["roles"]["adversarial"] is None

    disposition, status, reason = decide(_prepared(), observation, _audit())
    assert disposition.value == "INCONCLUSIVE"
    assert status.value == "ERROR"
    assert reason == "container cleanup was not independently confirmed"


def test_forged_driver_identity_and_unknown_prior_container_are_not_admissible(
    tmp_path: Path,
) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    forged_verifier = EvidenceVerifier(Settings(), store, _FakeSandbox(store, forged=True))
    forged = forged_verifier.evaluate(_input())
    # The raw resource was physically removed even though its forged source digest
    # leaves semantic evidence invalid.
    assert forged.cleanup_confirmed is True
    assert forged.control and forged.control.outcome is RoleOutcome.INVALID

    unknown_sandbox = _FakeSandbox(store, unknown=True)
    blocked = EvidenceVerifier(Settings(), store, unknown_sandbox).evaluate(_input("unknown"))
    assert blocked.feedback and blocked.feedback.gate == "operation-reconciliation"
    assert unknown_sandbox.calls == 0


@pytest.mark.parametrize(
    ("raw_image_id", "omit_raw_image_id"),
    [
        (None, True),
        (None, False),
        (1, False),
        ("sha256:other", False),
    ],
    ids=["missing", "null", "non-string", "mismatched"],
)
def test_raw_image_identity_must_be_a_matching_string(
    tmp_path: Path, raw_image_id: object, omit_raw_image_id: bool
) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    observation = EvidenceVerifier(
        Settings(),
        store,
        _FakeSandbox(
            store,
            raw_image_id=raw_image_id,
            omit_raw_image_id=omit_raw_image_id,
        ),
    ).evaluate(_input())

    assert observation.cleanup_confirmed is True
    assert observation.control and observation.control.outcome is RoleOutcome.INVALID
    assert observation.adversarial and observation.adversarial.outcome is RoleOutcome.INVALID
    disposition, status, _ = decide(_prepared(), observation, _audit())
    assert disposition.value == "INCONCLUSIVE"
    assert status.value == "COMPLETED"
    assert (
        EvidenceVerifier(Settings(), store).validate_saved(
            observation, _submission(), _prepared().manifest
        )
        is None
    )


def _saved_input(store: ArtifactStore, operation_id: str = "operation") -> EvidenceInput:
    """An input whose source blob is in ``store``, so saved evidence can re-validate."""
    source = store.put(b"admitted source", "application/x-tar")
    prepared = _prepared().model_copy(update={"source": source})
    return _input(operation_id).model_copy(update={"prepared": prepared})


def test_sandbox_seconds_travel_through_the_receipt_and_revalidate(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    sandbox = _FakeSandbox(store, host_usec=1_250_000, wall_usec=400_000, cpu_usec=650_000)
    verifier = EvidenceVerifier(Settings(), store, sandbox)

    observation = verifier.evaluate(_saved_input(store))

    for role in (observation.control, observation.adversarial):
        assert role is not None
        assert role.host_seconds == 1.25
        assert role.wall_seconds == 0.4
        assert role.cpu_seconds == 0.65
    assert observation.adversarial and observation.adversarial.outcome is RoleOutcome.VIOLATION
    # Saved evidence rebuilds each role from its raw receipt, timing included.
    assert verifier.validate_saved(observation, _submission(), _prepared().manifest) is not None


def test_receipts_without_sandbox_seconds_still_decode_and_revalidate(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    verifier = EvidenceVerifier(Settings(), store, _FakeSandbox(store))

    observation = verifier.evaluate(_saved_input(store))

    assert observation.control is not None
    assert observation.control.wall_seconds is None
    assert observation.control.cpu_seconds is None
    assert observation.control.host_seconds is None
    assert verifier.validate_saved(observation, _submission(), _prepared().manifest) is not None
    # A role observation serialized before the timing fields existed still decodes.
    saved = {"outcome": "PROPERTY_HELD", "target_executed": True, "covered_lines": [4]}
    assert RoleObservation.model_validate(saved).host_seconds is None


@pytest.mark.parametrize("bad", [-1, 1.5, "100", True, [1]])
def test_malformed_sandbox_seconds_are_unknown_and_never_change_the_outcome(
    tmp_path: Path, bad: object
) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    clean = EvidenceVerifier(Settings(), store, _FakeSandbox(store)).evaluate(_input("clean"))
    sandbox = _FakeSandbox(store, host_usec=bad, wall_usec=bad, cpu_usec=bad)
    verifier = EvidenceVerifier(Settings(), store, sandbox)

    observation = verifier.evaluate(_saved_input(store, "malformed"))

    for role in ("control", "adversarial"):
        timed, reference = getattr(observation, role), getattr(clean, role)
        assert timed == reference
    assert verifier.validate_saved(observation, _submission(), _prepared().manifest) is not None


def test_sandbox_seconds_never_reach_the_verdict(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    plain = EvidenceVerifier(Settings(), store, _FakeSandbox(store)).evaluate(_input("plain"))
    timed = EvidenceVerifier(
        Settings(), store, _FakeSandbox(store, host_usec=9_000_000, wall_usec=1, cpu_usec=1)
    ).evaluate(_input("timed"))

    assert decide(_prepared(), plain, _audit()) == decide(_prepared(), timed, _audit())


def test_prior_intent_and_competing_claim_prevent_operation_replay(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    sandbox = _FakeSandbox(store)
    verifier = EvidenceVerifier(Settings(), store, sandbox)
    request = _input("crashed")
    intent = store.put_json(
        {
            "schema_version": "corsair.evidence-intent/1",
            "operation_id": request.operation_id,
            "source_digest": request.prepared.source.sha256,
        }
    )
    assert store.claim(f"intent.{request.operation_id}", intent) is True
    assert store.claim(f"intent.{request.operation_id}", intent) is False

    blocked = verifier.evaluate(request)

    assert blocked.feedback and blocked.feedback.gate == "operation-reconciliation"
    assert blocked.cleanup_confirmed is False
    assert sandbox.calls == 0
    assert store.reconcile(request.operation_id) is None


def test_policy_never_refutes_negative_evidence_and_conditions_app_scope() -> None:
    observation = Observation(
        operation_id="op",
        source_digest=SOURCE_DIGEST,
        submission_digest="c" * 64,
        control=RoleObservation(
            outcome=RoleOutcome.HELD,
            target_executed=True,
            covered_lines=[4],
            reason="ok",
            native_exit_code=0,
        ),
        adversarial=RoleObservation(
            outcome=RoleOutcome.HELD,
            target_executed=True,
            covered_lines=[4],
            reason="blocked",
            native_exit_code=0,
        ),
        artifact=ArtifactRef(
            sha256=ARTIFACT_DIGEST,
            size=0,
            media_type="application/json",
        ),
        cleanup_confirmed=True,
    )
    disposition, status, _ = decide(_prepared(), observation, _audit())
    assert disposition.value == "INCONCLUSIVE"
    assert status.value == "COMPLETED"
    assert fix_status(observation).value == "DEMONSTRATION_BLOCKED"

    assert observation.adversarial is not None
    demonstrated = observation.model_copy(
        update={
            "adversarial": observation.adversarial.model_copy(
                update={"outcome": RoleOutcome.VIOLATION, "native_exit_code": 1}
            )
        }
    )
    application = _prepared().model_copy(
        update={
            "finding": _prepared().finding.model_copy(update={"claim_scope": Scope.APPLICATION})
        }
    )
    disposition, status, _ = decide(application, demonstrated, _audit())
    assert disposition.value == "CONDITIONAL"
    assert status.value == "COMPLETED"
    assert fix_status(demonstrated).value == "NOT_BLOCKED"


@pytest.mark.parametrize("boundary", ["recipe", "image", "budget", "capabilities"])
def test_reconciliation_rejects_stale_recipe_runtime_or_budget(tmp_path, boundary):
    store = ArtifactStore(tmp_path)
    sandbox = _FakeSandbox(store)
    verifier = EvidenceVerifier(Settings(), store, sandbox)
    request = _input()
    verifier.evaluate(request)
    if boundary == "recipe":
        recipe = request.prepared.recipe.model_copy(update={"expected_control": "changed"})
        prepared = request.prepared.model_copy(update={"recipe": recipe})
        changed = request.model_copy(update={"prepared": prepared})
    elif boundary == "image":
        manifest = request.prepared.manifest.model_copy(update={"image_id": "different"})
        prepared = request.prepared.model_copy(update={"manifest": manifest})
        changed = request.model_copy(update={"prepared": prepared})
    elif boundary == "capabilities":
        manifest = request.prepared.manifest.model_copy(
            update={"capabilities": {"verification": {"policy_revision": "changed"}}}
        )
        changed = request.model_copy(
            update={"prepared": request.prepared.model_copy(update={"manifest": manifest})}
        )
    else:
        changed = request.model_copy(update={"budget": Budget(probe_timeout_seconds=6)})
    with pytest.raises(ValueError, match="recipe/configuration"):
        verifier.evaluate(changed)
    assert sandbox.calls == 2


def test_driver_children_receive_only_the_fixed_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from corsair.adapters.sandboxing.drivers.python import driver

    monkeypatch.setenv("PATH", "/usr/local/bin:/usr/bin")
    monkeypatch.setenv("COVERAGE_CORE", "pytrace")
    monkeypatch.setenv("PYTHONPATH", "/source")
    assert driver._child_environment() == {
        "PATH": "/usr/local/bin:/usr/bin",
        "HOME": "/tmp",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "COVERAGE_FILE": "/work/.coverage",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        # sys.monitoring line measurement; an inherited core choice cannot override it.
        "COVERAGE_CORE": "sysmon",
    }


def test_driver_line_numbers_are_sorted_unique_positive_or_none() -> None:
    from corsair.adapters.sandboxing.drivers.python import driver

    assert driver._valid_line_numbers({4, 1, 3}) == [1, 3, 4]
    assert driver._valid_line_numbers([3, 3, 1]) == [1, 3]
    assert driver._valid_line_numbers([]) == []
    for invalid in (0, -1, True, "4", 4.0, None):
        assert driver._valid_line_numbers([1, invalid]) == []


_COVERAGE_TARGET = '''"""Module docstring
spanning lines."""


def decorate(function):
    return function


class Box:
    value = (
        1 +
        2
    )

    @decorate
    def get(self, flag):
        if flag:  # pragma: no cover
            return {
                "a": flag,
            }
        try:
            raise ValueError(
                "x"
            )
        except ValueError:
            pass
        return [item for item in range(3)
                if item]


def unused():
    return 1


Box().get(1)
Box().get(0)
'''


def test_driver_executed_lines_match_the_coverage_json_report(tmp_path: Path) -> None:
    import json
    import subprocess
    import sys

    from corsair.adapters.sandboxing.drivers.python import driver

    root = tmp_path.resolve()
    target = root / "target.py"
    target.write_text(_COVERAGE_TARGET, encoding="utf-8")
    data_file = root / ".coverage"
    environment = {"COVERAGE_FILE": str(data_file), "COVERAGE_CORE": "sysmon", "HOME": str(root)}
    coverage = [sys.executable, "-m", "coverage"]
    subprocess.run(
        [*coverage, "run", f"--source={root}", str(target)], cwd=root, env=environment, check=True
    )
    report = root / "coverage.json"
    subprocess.run(
        [*coverage, "json", "-o", str(report)],
        cwd=root,
        env=environment,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    expected = json.loads(report.read_text(encoding="utf-8"))["files"]
    (entry,) = expected.values()

    in_process = root / "in-process.json"

    def executed(source: Path | str, data: Path = data_file) -> list[int]:
        return driver._executed_lines(data, str(source), in_process)

    # Identical to the command-line report: continuation lines map to their statement's
    # first line, and an unexecuted function body stays absent.
    assert executed(target) == entry["executed_lines"]
    assert {5, 9, 10, 27, 31, 35, 36} <= set(executed(target))
    assert not {11, 12, 28, 32} & set(executed(target))
    assert executed(root / "absent.py") == []
    assert executed(target, root / "missing.coverage") == []
    target.write_text("def broken(:\n", encoding="utf-8")
    assert executed(target) == []


def test_driver_reads_container_cpu_usage_from_cgroup_v2(tmp_path: Path) -> None:
    from corsair.adapters.sandboxing.drivers.python import driver

    stat = tmp_path / "cpu.stat"
    stat.write_text("usage_usec 15025\nuser_usec 7512\nsystem_usec 7512\n", encoding="utf-8")
    assert driver._cgroup_cpu_usec(stat) == 15025
    assert driver._cgroup_cpu_usec(tmp_path / "absent.stat") is None
    stat.write_text("user_usec 7512\n", encoding="utf-8")
    assert driver._cgroup_cpu_usec(stat) is None
    stat.write_text("usage_usec many\n", encoding="utf-8")
    assert driver._cgroup_cpu_usec(stat) is None


def test_driver_timing_fields_are_omitted_when_unknown() -> None:
    from corsair.adapters.sandboxing.drivers.python import driver

    assert driver._timing(wall_usec=12, cpu_usec=None) == {"wall_usec": 12}
    assert driver._timing(wall_usec=12, cpu_usec=34) == {"wall_usec": 12, "cpu_usec": 34}


# ERROR observations: receipt coverage and a code-owned error kind, never a verdict input.

KERNEL_CASES = Path(__file__).resolve().parents[1] / "replay" / "kernel"
ERROR_REASON = "native target execution or observer reporting failed"


@pytest.mark.parametrize(
    ("lines", "coverage_file", "kind", "covered", "executed", "error_kind"),
    [
        ((4,), None, "execution_error", [4], True, "target_exception"),
        ((1, 2), None, "execution_error", [1, 2], False, "target_exception"),
        ((), None, "execution_error", [], False, "target_exception"),
        ((4,), "other.py", "execution_error", [], False, "target_exception"),
        ((4,), None, None, [4], True, "harness"),
        ((4,), None, "disclosure", [4], True, "harness"),
    ],
    ids=["bound-line", "other-lines", "no-lines", "other-file", "no-kind", "other-kind"],
)
def test_error_receipt_keeps_recipe_module_coverage_and_its_error_kind(
    tmp_path: Path,
    lines: tuple[int, ...],
    coverage_file: str | None,
    kind: object,
    covered: list[int],
    executed: bool,
    error_kind: ErrorKind,
) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    sandbox = _FakeSandbox(
        store,
        adversarial_error=True,
        error_kind=kind,
        error_lines=lines,
        error_coverage_file=coverage_file,
    )
    observation = EvidenceVerifier(Settings(), store, sandbox).evaluate(_input())

    assert observation.adversarial == RoleObservation(
        outcome=RoleOutcome.ERROR,
        target_executed=executed,
        covered_lines=covered,
        reason=ERROR_REASON,
        native_exit_code=1,
        error_kind=error_kind,
    )
    assert observation.control and observation.control.error_kind is None
    assert decide(_prepared(), observation, _audit())[1:] == (
        ExecutionStatus.ERROR,
        "trusted probe execution errored",
    )


def test_fixed_source_error_counts_any_recipe_module_line(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    request = _input()
    sandbox = _FakeSandbox(store, adversarial_error=True, error_lines=(1,))
    raw = sandbox.execute_role(
        request.prepared,
        request.submission,
        "adversarial",
        request.budget,
        lambda: None,
        operation_id=request.operation_id,
    )
    verifier = EvidenceVerifier(Settings(), store)
    common: dict[str, Any] = {
        "expected_operation": request.operation_id,
        "expected_role": "adversarial",
        "expected_source": request.prepared.source.sha256,
        "expected_submission": digest(request.submission),
        "prepared": request.prepared,
    }
    vulnerable, vulnerable_valid = verifier._validate_raw(raw, fixed=False, **common)
    fixed, fixed_valid = verifier._validate_raw(raw, fixed=True, **common)

    # Line 1 is not the bound line 4, but fixed source may delete the finding line.
    assert (vulnerable.target_executed, fixed.target_executed) == (False, True)
    assert vulnerable.covered_lines == fixed.covered_lines == [1]
    # An ERROR role is never admitted as valid evidence, with or without coverage.
    assert (vulnerable_valid, fixed_valid) == (False, False)


def test_sandbox_faults_are_classified_sandbox(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    receipt = EvidenceVerifier(
        Settings(), store, _FakeSandbox(store, receipt_error="SandboxExecutionError")
    ).evaluate(_input("receipt"))
    assert receipt.adversarial == RoleObservation(
        outcome=RoleOutcome.ERROR,
        target_executed=False,
        reason="trusted sandbox execution failed",
        error_kind="sandbox",
    )

    lost = EvidenceVerifier(
        Settings(), store, _FakeSandbox(store, raises={"control": SandboxUnavailable("lost")})
    ).evaluate(_input("lost"))
    assert lost.control and lost.control.error_kind == "sandbox"
    assert lost.control.reason == "trusted sandbox became unavailable"
    assert lost.adversarial and lost.adversarial.error_kind == "sandbox"
    assert lost.adversarial.reason == "role was not executed"

    failed = EvidenceVerifier(
        Settings(), store, _FakeSandbox(store, raises={"adversarial": RuntimeError("boom")})
    ).evaluate(_input("failed"))
    assert failed.adversarial == RoleObservation(
        outcome=RoleOutcome.ERROR,
        target_executed=False,
        reason="trusted sandbox role execution failed",
        error_kind="sandbox",
    )


def test_error_kind_belongs_only_to_error_outcomes() -> None:
    with pytest.raises(ValidationError, match="error_kind"):
        RoleObservation(outcome=RoleOutcome.HELD, target_executed=True, error_kind="harness")
    with pytest.raises(ValidationError):
        RoleObservation.model_validate(
            {"outcome": "ERROR", "target_executed": False, "error_kind": "model"}
        )
    # An ERROR observation saved before the field existed decodes with the kind unknown.
    saved = RoleObservation.model_validate(_SAVED_BEFORE_ERROR_KIND["error"])
    assert saved.error_kind is None
    assert (saved.target_executed, saved.covered_lines) == (False, [])


def _error_role(covered: bool, line: int) -> RoleObservation:
    """An ERROR role as saved before (no coverage, no kind) and as built now."""
    if not covered:
        return RoleObservation.model_validate(_SAVED_BEFORE_ERROR_KIND["error"])
    return RoleObservation(
        outcome=RoleOutcome.ERROR,
        target_executed=True,
        covered_lines=[line],
        reason=ERROR_REASON,
        native_exit_code=1,
        error_kind="target_exception",
    )


def _healthy(role: str) -> RoleObservation:
    outcome = RoleOutcome.HELD if role == "control" else RoleOutcome.VIOLATION
    return RoleObservation(
        outcome=outcome,
        target_executed=True,
        covered_lines=[4],
        native_exit_code=0 if role == "control" else 1,
    )


@pytest.mark.parametrize("errored", ["control", "adversarial"])
@pytest.mark.parametrize("decision", [AuditDecision.ACCEPT, AuditDecision.REJECT])
def test_decide_is_unchanged_by_coverage_on_an_error_role(
    errored: str, decision: AuditDecision
) -> None:
    prepared = _prepared()
    assert prepared.bound_line == 4
    other = "adversarial" if errored == "control" else "control"
    decisions = set()
    for covered in (False, True):
        observation = Observation(
            operation_id="operation",
            source_digest=SOURCE_DIGEST,
            submission_digest="c" * 64,
            artifact=ArtifactRef(sha256=ARTIFACT_DIGEST, size=1, media_type="application/json"),
            cleanup_confirmed=True,
        ).model_copy(update={errored: _error_role(covered, 4), other: _healthy(other)})
        outcome = session_verdict(prepared, observation, _audit(decision), FixStatus.NOT_REQUESTED)
        decisions.add(
            (
                decide(prepared, observation, _audit(decision)),
                outcome.verdict,
                outcome.reason,
                outcome.clean_negative,
                fix_status(observation),
            )
        )
    assert decisions == {
        (
            (Disposition.INCONCLUSIVE, ExecutionStatus.ERROR, "trusted probe execution errored"),
            Verdict.ERROR,
            "trusted probe execution errored",
            False,
            FixStatus.UNVERIFIED,
        )
    }


def _with_error_role(item: RoundResult, role: str, covered: bool, line: int) -> RoundResult:
    assert item.observation is not None
    observation = item.observation.model_copy(update={role: _error_role(covered, line)})
    return item.model_copy(update={"observation": observation})


def test_every_committed_kernel_case_replays_with_or_without_error_coverage() -> None:
    """Coverage on an ERROR role never moves a committed kernel case's verdict."""
    from corsair.evaluation.gym.capture import kernel_verdict

    paths = sorted(KERNEL_CASES.glob("*.json"))
    assert paths
    variants = 0
    for path in paths:
        case = KernelCase.model_validate_json(path.read_bytes())
        assert kernel_verdict(case) == case.recorded_verdict, path.name
        line = case.prepared.bound_line if case.prepared is not None else None
        for position, item in enumerate(case.rounds):
            if item.observation is None or line is None:
                continue
            for role in ("control", "adversarial"):
                verdicts = set()
                for covered in (False, True):
                    rounds = list(case.rounds)
                    rounds[position] = _with_error_role(item, role, covered, line)
                    verdicts.add(kernel_verdict(case.model_copy(update={"rounds": rounds})))
                    variants += 1
                assert len(verdicts) == 1, (path.name, position, role)
    assert variants > 0


# Role observations exactly as the evidence verifier at 39091887 committed them (from
# a store it wrote): an ERROR role kept neither the receipt's coverage nor any kind.
_SAVED_BEFORE_ERROR_KIND: dict[str, dict[str, Any]] = {
    "control": {
        "covered_lines": [4],
        "cpu_seconds": None,
        "host_seconds": None,
        "native_exit_code": 0,
        "outcome": "PROPERTY_HELD",
        "reason": "validated native pytest/coverage evidence",
        "target_executed": True,
        "wall_seconds": None,
    },
    "violation": {
        "covered_lines": [4],
        "cpu_seconds": None,
        "host_seconds": None,
        "native_exit_code": 1,
        "outcome": "VIOLATION",
        "reason": "validated native pytest/coverage evidence",
        "target_executed": True,
        "wall_seconds": None,
    },
    "error": {
        "covered_lines": [],
        "cpu_seconds": None,
        "host_seconds": None,
        "native_exit_code": 1,
        "outcome": "ERROR",
        "reason": ERROR_REASON,
        "target_executed": False,
        "wall_seconds": None,
    },
}


def _commit_saved_before_error_kind(
    store: ArtifactStore, operation_id: str, adversarial: str
) -> Observation:
    """Commit one operation in the byte shape 39091887 wrote: same bundle, old role JSON."""
    request = _saved_input(store, operation_id)
    sandbox = _FakeSandbox(store, adversarial_error=adversarial == "error")
    raw = {
        role: sandbox.execute_role(
            request.prepared,
            request.submission,
            role,
            request.budget,
            lambda: None,
            operation_id=operation_id,
        )
        for role in ("control", "adversarial")
    }
    bundle = store.put_json(
        {
            "schema_version": "corsair.evidence/1",
            "operation_id": operation_id,
            "source_digest": request.prepared.source.sha256,
            "submission_digest": digest(request.submission),
            "prepared": store.put_json(request.prepared).model_dump(mode="json"),
            "fixed": False,
            "roles": {role: ref.model_dump(mode="json") for role, ref in raw.items()},
        }
    )
    saved = {
        "adversarial": _SAVED_BEFORE_ERROR_KIND[adversarial],
        "artifact": bundle.model_dump(mode="json"),
        "cleanup_confirmed": True,
        "control": _SAVED_BEFORE_ERROR_KIND["control"],
        "feedback": None,
        "operation_id": operation_id,
        "source_digest": request.prepared.source.sha256,
        "submission_digest": digest(request.submission),
    }
    store.commit(operation_id, store.put_json(saved))
    return Observation.model_validate(saved)


def test_results_saved_before_error_kind_revalidate_as_before(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    verifier = EvidenceVerifier(Settings(), store)
    manifest = _prepared().manifest

    # A result without an ERROR role rebuilds exactly as saved and still re-validates.
    held = _commit_saved_before_error_kind(store, "saved-violation", "violation")
    assert verifier.validate_saved(held, _submission(), manifest) is not None

    # A saved ERROR role decodes in its old shape and, as before, never re-validates:
    # an ERROR role is not admissible evidence whatever coverage its receipt reports.
    errored = _commit_saved_before_error_kind(store, "saved-error", "error")
    assert errored.adversarial is not None
    assert errored.adversarial.error_kind is None
    assert errored.adversarial.covered_lines == []
    assert verifier.validate_saved(errored, _submission(), manifest) is None

    # The same receipt evaluated now keeps its coverage; the decision is unchanged.
    current = EvidenceVerifier(
        Settings(), store, _FakeSandbox(store, adversarial_error=True)
    ).evaluate(_saved_input(store, "current-error"))
    assert current.adversarial is not None
    assert current.adversarial.covered_lines == [4]
    assert current.adversarial.error_kind == "target_exception"
    assert verifier.validate_saved(current, _submission(), manifest) is None
    assert decide(_prepared(), errored, _audit()) == decide(_prepared(), current, _audit())
    bundle = store.get_json(current.artifact) if current.artifact else {}
    rebuilt, valid = verifier._validate_raw(
        ArtifactRef.model_validate(bundle["roles"]["adversarial"]),
        expected_operation="current-error",
        expected_role="adversarial",
        expected_source=current.source_digest,
        expected_submission=digest(_submission()),
        prepared=PreparedCase.model_validate(
            store.get_json(ArtifactRef.model_validate(bundle["prepared"]))
        ),
        fixed=False,
    )
    assert (rebuilt, valid) == (current.adversarial, False)
