from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    ArtifactRef,
    AuditDecision,
    AuditOutput,
    AuditResult,
    Budget,
    EvidenceInput,
    Finding,
    Observation,
    PlanRevision,
    PreparedCase,
    PythonRecipe,
    RoleObservation,
    RoleOutcome,
    RunManifest,
    Scope,
    Submission,
    digest,
)
from corsair.policies.verdicts import decide, fix_status
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

    def has_unknown_operation(self, operation_id: str) -> bool:
        del operation_id  # Test-controlled operation state, independent of its identity.
        return self.unknown

    def execute_role(self, prepared, submission, role, budget, heartbeat, *, operation_id):
        store = self.store
        del budget, heartbeat
        self.calls += 1
        violation = role == "adversarial"
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
            "coverage_file": "reader.py",
        }
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
            "docker_exit_code": 1 if violation else 0,
            "driver": driver,
        }
        if not self.omit_raw_image_id:
            raw["image_id"] = self.raw_image_id
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
    return AuditOutput(review=AuditResult(decision=decision, rule="evidence", reason="reviewed"))


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
    from corsair.adapters.sandboxing import driver

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
    from corsair.adapters.sandboxing import driver

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

    from corsair.adapters.sandboxing import driver

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
