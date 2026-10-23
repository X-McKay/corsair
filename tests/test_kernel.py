"""The kernel's gates and verdicts against the scripted sandbox double; no containers, no model."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from corsair.adapters.artifacts.filesystem import ArtifactStore
from corsair.adapters.frameworks import framework
from corsair.adapters.frameworks.pytest_ import ast_guard
from corsair.application.cases import load_case
from corsair.application.kernel import Kernel, environment_key, reported_target_present, target_binding
from corsair.domain.policy import negative_verdict, terminal_verdict
from corsair.domain.verification import AuditResult, Fix, Gate, Hypothesis, Label, Outcome, Submission
from corsair.runtime import matrix
from tests.fakes import FakeSandboxes, Script

pytestmark = pytest.mark.anyio

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "cases/path-traversal-fixture"
REFERENCE = Submission.model_validate_json((CASE / "reference-submission.json").read_text())
ROW = matrix.load()[0]

HAPPY = {
    ("vulnerable", "control"): Script("holds"),
    ("vulnerable", "exploit"): Script("violated", "AssertionError", "outside content returned"),
    ("fixed", "control"): Script("holds"),
    ("fixed", "exploit"): Script("holds"),
}


def kernel(fake: FakeSandboxes, tmp_path: Path, *, auditor=None, case_path: Path = CASE) -> Kernel:
    case = load_case(case_path)
    return Kernel(
        fake,
        ROW,
        case,
        artifacts=ArtifactStore(tmp_path / "artifacts"),
        auditor=auditor,
        run_id="run1",
        framework=framework(ROW.framework),
    )


async def accept(submission: Submission) -> AuditResult:
    return AuditResult(valid=True, reason="fair differential test")


# --- gate 1 -------------------------------------------------------------------------------------------------------


def test_ast_guard_requires_the_three_symbols_and_one_payload_argument():
    assert ast_guard(REFERENCE.probe).passed
    missing = ast_guard("CONTROL_PAYLOAD = 1\ndef run_target(p): pass\n")
    assert not missing.passed and "EXPLOIT_PAYLOAD" in missing.reason
    arity = ast_guard("CONTROL_PAYLOAD = 1\nEXPLOIT_PAYLOAD = 2\ndef run_target(p, q): pass\n")
    assert not arity.passed and "exactly one" in arity.reason
    broken = ast_guard("def (:\n")
    assert not broken.passed and broken.stage is Gate.AST_GUARD


@pytest.mark.parametrize(
    "line",
    [
        "from unittest import mock",
        "import unittest.mock",
        "from unittest.mock import patch",
        "import pytest_mock",
        "import responses",
    ],
)
def test_ast_guard_bans_mocking_libraries(line):
    verdict = ast_guard(f"{line}\nCONTROL_PAYLOAD = 1\nEXPLOIT_PAYLOAD = 2\ndef run_target(p): pass\n")
    assert not verdict.passed and "mocking" in verdict.reason


# --- the whole evaluation -----------------------------------------------------------------------------------------


async def test_verified_submission_runs_both_payloads_on_both_revisions_and_verifies_the_fix(tmp_path):
    fake = FakeSandboxes(dict(HAPPY))
    audited: list[Submission] = []

    async def auditor(submission: Submission) -> AuditResult:
        audited.append(submission)
        return AuditResult(valid=True, reason="ok")

    evaluation = await kernel(fake, tmp_path, auditor=auditor).evaluate(REFERENCE)
    assert evaluation.gate.passed and evaluation.gate.stage is Gate.VERIFIED
    verdict = evaluation.verdict
    assert verdict is not None
    assert verdict.label is Label.LIKELY_EXPLOITABLE and verdict.rule == "K1"
    assert verdict.fix is Fix.VERIFIED
    assert [(r.revision, r.role, r.outcome) for r in verdict.runs] == [
        ("vulnerable", "control", Outcome.HOLDS),
        ("vulnerable", "exploit", Outcome.VIOLATED),
        ("fixed", "control", Outcome.HOLDS),
        ("fixed", "exploit", Outcome.HOLDS),
    ]
    assert all(run.junit_tests == 1 and run.junit is not None for run in verdict.runs)
    assert verdict.runs[0].covered_lines == (4,)
    assert audited == [REFERENCE]
    # two builds (one per revision), four fresh probe sandboxes, every sandbox removed
    assert [spec.labels["corsair.lite.stage"] for spec in fake.creates] == ["build", "build"]
    assert len(fake.opened) == 4 and len(set(fake.opened)) == 4
    assert set(fake.removed) >= set(fake.opened) | {spec.name for spec in fake.creates}
    assert fake.labelled() == []
    # the vulnerable and fixed environments have different keys, and a probe never gets network
    assert len(set(fake.sealed.values())) == 2
    assert all(spec.network == "none" for spec in fake.creates)  # empty build script: no network at all


async def test_build_script_gets_network_only_during_the_build_and_is_cached_by_exact_key(tmp_path):
    fake = FakeSandboxes(dict(HAPPY))
    with_build = REFERENCE.model_copy(update={"build_script": "pip install -e ."})
    k = kernel(fake, tmp_path)
    first = await k.evaluate(with_build)
    assert first.verdict is not None
    assert [spec.network for spec in fake.creates] == ["build", "build"]
    drops = [argv for _, argv in fake.execs if argv == ("<drop-network>",)]
    assert len(drops) == 2
    builds_before = len(fake.creates)
    second = await k.evaluate(with_build)
    assert (
        second.verdict is not None and len(fake.creates) == builds_before
    )  # cache hit, no new build sandbox
    other = with_build.model_copy(update={"build_script": "pip install -e .[test]"})
    await k.evaluate(other)
    assert len(fake.creates) == builds_before + 2
    case = load_case(CASE)
    assert environment_key(ROW, case.revision.tree_sha256, "a") != environment_key(
        ROW, case.revision.tree_sha256, "b"
    )


async def test_failed_build_returns_the_tail_and_runs_nothing(tmp_path):
    fake = FakeSandboxes(dict(HAPPY), build_exit={"vulnerable": 1})
    evaluation = await kernel(fake, tmp_path).evaluate(
        REFERENCE.model_copy(update={"build_script": "pip install x"})
    )
    assert not evaluation.gate.passed and evaluation.gate.stage is Gate.BUILD_REPLAY
    assert "no matching distribution" in evaluation.gate.stderr_tail
    assert evaluation.runs == () and fake.opened == []
    assert terminal_verdict(evaluation.gate, 1).label is Label.UNABLE_TO_RUN


async def test_control_must_hold_before_the_exploit_runs(tmp_path):
    fake = FakeSandboxes(
        {**HAPPY, ("vulnerable", "control"): Script("errored", "FileNotFoundError", "no such file")}
    )
    evaluation = await kernel(fake, tmp_path).evaluate(REFERENCE)
    assert evaluation.gate.stage is Gate.CONTROL_RUN and "FileNotFoundError" in evaluation.gate.reason
    assert [r.role for r in evaluation.runs] == ["control"]
    assert terminal_verdict(evaluation.gate, 2).label is Label.INCONCLUSIVE


async def test_control_that_never_reaches_the_target_lines_is_rejected(tmp_path):
    fake = FakeSandboxes({**HAPPY, ("vulnerable", "control"): Script("holds", covered_lines=())})
    evaluation = await kernel(fake, tmp_path).evaluate(REFERENCE)
    assert evaluation.gate.stage is Gate.CONTROL_COVERAGE and "lines [4]" in evaluation.gate.reason


async def test_exploit_that_holds_is_not_a_demonstration(tmp_path):
    fake = FakeSandboxes({**HAPPY, ("vulnerable", "exploit"): Script("holds")})
    evaluation = await kernel(fake, tmp_path).evaluate(REFERENCE)
    assert evaluation.gate.stage is Gate.EXPLOIT_RUN and "not demonstrated" in evaluation.gate.reason
    assert evaluation.verdict is None


async def test_exploit_crash_or_application_assertion_is_errored_not_violated(tmp_path):
    crash = FakeSandboxes({**HAPPY, ("vulnerable", "exploit"): Script("errored", "TypeError", "bad arg")})
    evaluation = await kernel(crash, tmp_path).evaluate(REFERENCE)
    assert evaluation.gate.stage is Gate.EXPLOIT_RUN and "TypeError" in evaluation.gate.reason
    app_assert = FakeSandboxes(
        {
            **HAPPY,
            ("vulnerable", "exploit"): Script("violated", "AssertionError", "app", raised_in_probe=False),
        }
    )
    evaluation = await kernel(app_assert, tmp_path).evaluate(REFERENCE)
    assert evaluation.gate.stage is Gate.EXPLOIT_RUN and evaluation.runs[-1].outcome is Outcome.ERRORED


async def test_exploit_without_target_coverage_is_rejected(tmp_path):
    fake = FakeSandboxes(
        {**HAPPY, ("vulnerable", "exploit"): Script("violated", "AssertionError", "x", covered_lines=())}
    )
    evaluation = await kernel(fake, tmp_path).evaluate(REFERENCE)
    assert evaluation.gate.stage is Gate.EXPLOIT_COVERAGE


async def test_blind_audit_rejection_blocks_the_verdict_after_the_deterministic_gates(tmp_path):
    async def reject(submission: Submission) -> AuditResult:
        return AuditResult(valid=False, reason="run_target branches on the payload")

    fake = FakeSandboxes(dict(HAPPY))
    evaluation = await kernel(fake, tmp_path, auditor=reject).evaluate(REFERENCE)
    assert evaluation.gate.stage is Gate.BLIND_AUDIT and "branches" in evaluation.gate.reason
    assert evaluation.verdict is None and len(evaluation.runs) == 2  # the fixed revision never ran


async def test_fix_not_verified_when_the_exploit_still_violates_on_the_fixed_revision(tmp_path):
    fake = FakeSandboxes({**HAPPY, ("fixed", "exploit"): Script("violated", "AssertionError", "still")})
    evaluation = await kernel(fake, tmp_path, auditor=accept).evaluate(REFERENCE)
    assert evaluation.verdict is not None and evaluation.verdict.label is Label.LIKELY_EXPLOITABLE
    assert evaluation.verdict.fix is Fix.NOT_VERIFIED and "still violates" in evaluation.verdict.fix_reason


async def test_fixed_build_failure_leaves_the_finding_and_marks_the_fix_unverified(tmp_path):
    fake = FakeSandboxes(dict(HAPPY), build_exit={"fixed": 1})
    evaluation = await kernel(fake, tmp_path).evaluate(
        REFERENCE.model_copy(update={"build_script": "pip install ."})
    )
    assert evaluation.verdict is not None and evaluation.verdict.label is Label.LIKELY_EXPLOITABLE
    assert evaluation.verdict.fix is Fix.NOT_VERIFIED and "did not build" in evaluation.verdict.fix_reason


async def test_collection_failure_is_not_run_and_timeout_is_infra(tmp_path):
    not_run = FakeSandboxes({**HAPPY, ("vulnerable", "control"): Script("not_run")})
    evaluation = await kernel(not_run, tmp_path).evaluate(REFERENCE)
    assert evaluation.gate.stage is Gate.CONTROL_RUN and evaluation.runs[0].outcome is Outcome.NOT_RUN
    timeout = FakeSandboxes({**HAPPY, ("vulnerable", "exploit"): Script("timeout")})
    evaluation = await kernel(timeout, tmp_path).evaluate(REFERENCE)
    assert evaluation.gate.stage is Gate.INFRA and evaluation.runs[-1].outcome is Outcome.INFRA
    assert terminal_verdict(evaluation.gate, 1).label is Label.ERROR


async def test_native_report_and_driver_record_must_agree(tmp_path):
    fake = FakeSandboxes({**HAPPY, ("vulnerable", "control"): Script("holds", junit_disagrees=True)})
    evaluation = await kernel(fake, tmp_path).evaluate(REFERENCE)
    assert evaluation.runs[0].outcome is Outcome.ERRORED and "disagrees" in (evaluation.runs[0].message or "")


async def test_held_sandbox_identity_is_never_reused_or_removed(tmp_path):
    fake = FakeSandboxes(dict(HAPPY))
    k = kernel(fake, tmp_path)
    from corsair.ports.sandbox import SandboxSpec, labels

    held = SandboxSpec(
        image=ROW.image,
        workdir="/work",
        labels=labels(
            "run1",
            "build",
            revision="vulnerable",
            env=environment_key(ROW, k.case.revision.tree_sha256, "", "sha256:fake", "documents.py")[:16],
        ),
    ).name
    fake.held.add(held)
    evaluation = await k.evaluate(REFERENCE)
    assert evaluation.gate.stage is Gate.INFRA and "SandboxExists" in evaluation.gate.reason
    assert held not in fake.removed


def test_no_runtime_row_and_no_submission_terminal_verdicts():
    assert terminal_verdict(None, 0).label is Label.ERROR


def test_submission_digest_is_stable_and_hypothesis_lines_are_sorted_unique():
    assert (
        REFERENCE.sha256
        == Submission.model_validate_json(json.dumps(REFERENCE.model_dump(mode="json"))).sha256
    )
    hypothesis = Hypothesis(
        target_file="a.py", target_symbol="f", target_lines=(9, 3, 3), root_cause="x", expected_violation="y"
    )
    assert hypothesis.target_lines == (3, 9)
    with pytest.raises(ValueError):
        Hypothesis(
            target_file="/abs.py",
            target_symbol="f",
            target_lines=(1,),
            root_cause="x",
            expected_violation="y",
        )


async def test_fixed_exploit_raising_a_non_assertion_keeps_the_label_but_asks_for_a_fix_correction(tmp_path):
    fake = FakeSandboxes(
        {**HAPPY, ("fixed", "exploit"): Script("errored", "ValueError", "not in the subpath")}
    )
    evaluation = await kernel(fake, tmp_path, auditor=accept).evaluate(REFERENCE)
    assert evaluation.gate.stage is Gate.FIX_RUN and not evaluation.gate.passed
    assert "ValueError" in evaluation.gate.reason and "catch it inside run_target" in evaluation.gate.reason
    assert evaluation.verdict is not None and evaluation.verdict.label is Label.LIKELY_EXPLOITABLE
    assert evaluation.verdict.fix is Fix.NOT_VERIFIED
    assert evaluation.submission == REFERENCE


async def test_hypothesis_must_target_the_reported_file_and_an_absent_target_is_decided_without_a_sandbox(
    tmp_path,
):
    fake = FakeSandboxes(dict(HAPPY))
    k = kernel(fake, tmp_path)
    other = REFERENCE.model_copy(
        update={"hypothesis": REFERENCE.hypothesis.model_copy(update={"target_file": "other.py"})}
    )
    evaluation = await k.evaluate(other)
    assert evaluation.gate.stage is Gate.TARGET_BINDING and "reports documents.py" in evaluation.gate.reason
    assert fake.creates == [] and evaluation.runs == ()
    assert reported_target_present(k.case) is None
    missing = k.case.model_copy(
        update={"finding": k.case.finding.model_copy(update={"file_path": "maintenance/logs.py"})}
    )
    assert "does not exist" in (reported_target_present(missing) or "")
    unnamed = k.case.model_copy(update={"finding": k.case.finding.model_copy(update={"file_path": None})})
    assert target_binding(unnamed, REFERENCE.hypothesis).passed
    assert not target_binding(unnamed, other.hypothesis).passed  # other.py is not in the tree either


async def test_symbol_and_lines_must_exist_in_the_target_file(tmp_path):
    fake = FakeSandboxes(dict(HAPPY))
    k = kernel(fake, tmp_path)
    wrong_symbol = REFERENCE.model_copy(
        update={"hypothesis": REFERENCE.hypothesis.model_copy(update={"target_symbol": "rotate_logs"})}
    )
    evaluation = await k.evaluate(wrong_symbol)
    assert evaluation.gate.stage is Gate.TARGET_BINDING and "does not appear" in evaluation.gate.reason
    far = REFERENCE.model_copy(
        update={"hypothesis": REFERENCE.hypothesis.model_copy(update={"target_lines": (4, 400)})}
    )
    evaluation = await k.evaluate(far)
    assert evaluation.gate.stage is Gate.TARGET_BINDING and "out of range" in evaluation.gate.reason
    assert fake.creates == []


# --- clean negatives (K4) ------------------------------------------------------------------------------------------------

NEGATIVE = {**HAPPY, ("vulnerable", "exploit"): Script("holds")}


async def test_held_exploit_with_target_coverage_is_a_clean_negative_and_the_fix_is_not_run(tmp_path):
    fake = FakeSandboxes(dict(NEGATIVE))
    evaluation = await kernel(fake, tmp_path, auditor=accept).evaluate(REFERENCE)
    assert evaluation.clean_negative and evaluation.verdict is None
    assert evaluation.gate.stage is Gate.EXPLOIT_RUN and "clean negative" in evaluation.gate.reason
    assert [(r.revision, r.role, r.outcome) for r in evaluation.runs] == [
        ("vulnerable", "control", Outcome.HOLDS),
        ("vulnerable", "exploit", Outcome.HOLDS),
    ]  # no fixed-revision runs
    assert evaluation.audit is not None and evaluation.audit.valid
    verdict = negative_verdict([evaluation], threshold=1)
    assert verdict is not None and verdict.label is Label.LIKELY_NOT_EXPLOITABLE and verdict.rule == "K4"
    assert verdict.fix is Fix.NOT_APPLICABLE and len(verdict.runs) == 2


async def test_held_exploit_without_target_coverage_is_not_a_clean_negative(tmp_path):
    fake = FakeSandboxes({**HAPPY, ("vulnerable", "exploit"): Script("holds", covered_lines=())})
    evaluation = await kernel(fake, tmp_path).evaluate(REFERENCE)
    assert not evaluation.clean_negative and evaluation.gate.stage is Gate.EXPLOIT_RUN
    assert "did not execute" in evaluation.gate.reason
    assert negative_verdict([evaluation], threshold=1) is None


async def test_a_clean_negative_must_also_pass_the_blind_audit(tmp_path):
    async def reject(submission: Submission) -> AuditResult:
        return AuditResult(valid=False, reason="the exploit payload is outside the accepted type")

    fake = FakeSandboxes(dict(NEGATIVE))
    evaluation = await kernel(fake, tmp_path, auditor=reject).evaluate(REFERENCE)
    assert not evaluation.clean_negative and evaluation.gate.stage is Gate.BLIND_AUDIT
    assert negative_verdict([evaluation], threshold=1) is None


async def test_negative_threshold_counts_distinct_submissions_and_an_exploitable_one_always_wins(tmp_path):
    fake = FakeSandboxes(dict(NEGATIVE))
    k = kernel(fake, tmp_path, auditor=accept)
    first = await k.evaluate(REFERENCE)
    again = await k.evaluate(REFERENCE)  # the same submission digest counts once
    assert negative_verdict([first, again], threshold=2) is None
    second = await k.evaluate(REFERENCE.model_copy(update={"probe": REFERENCE.probe + "\n# second\n"}))
    verdict = negative_verdict([first, again, second], threshold=2)
    assert (
        verdict is not None
        and verdict.label is Label.LIKELY_NOT_EXPLOITABLE
        and "2 distinct" in verdict.reason
    )
    with pytest.raises(ValueError):
        negative_verdict([first], threshold=0)
    fake.scenario[("vulnerable", "exploit")] = Script(
        "violated", "AssertionError", "outside content returned"
    )
    exploitable = await k.evaluate(REFERENCE)
    assert exploitable.verdict is not None and exploitable.verdict.label is Label.LIKELY_EXPLOITABLE
    assert negative_verdict([first, second, exploitable], threshold=2) is None


async def test_failing_fix_keeps_the_exploitable_label_with_the_fix_not_verified(tmp_path):
    fake = FakeSandboxes(
        {**HAPPY, ("fixed", "control"): Script("errored", "ValueError", "fixed setup fails")}
    )
    evaluation = await kernel(fake, tmp_path, auditor=accept).evaluate(REFERENCE)
    assert evaluation.verdict is not None and evaluation.verdict.label is Label.LIKELY_EXPLOITABLE
    assert evaluation.verdict.fix is Fix.NOT_VERIFIED and evaluation.gate.passed
