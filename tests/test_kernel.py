"""The kernel's gates and verdicts against the scripted sandbox double; no containers, no model."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from corsair import matrix
from corsair.artifacts import ArtifactStore
from corsair.case import load_case
from corsair.frameworks.pytest_ import Pytest
from corsair.kernel import (AuditResult, Fix, Gate, Hypothesis, Kernel, Label, RevisionDisposition,
                            RoleResult, Submission, ast_guard, environment_key, reported_target_present,
                            role_result, target_binding, terminal_verdict)
from tests.fakes import FakeSandboxes, Script
from corsair.sandbox.port import Exec

pytestmark = pytest.mark.anyio

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "cases/cs-0001-a"
REFERENCE = Submission.model_validate_json((CASE / "reference-submission.json").read_text())
ROW = matrix.load()[0]

HAPPY = {("vulnerable", "control"): Script("holds"),
         ("vulnerable", "exploit"): Script("violated", "AssertionError", "outside content returned"),
         ("fixed", "control"): Script("holds"),
         ("fixed", "exploit"): Script("holds")}


async def accept(submission: Submission) -> AuditResult:
    return AuditResult(valid=True, reason="fair differential test")


def kernel(fake: FakeSandboxes, tmp_path: Path, *, auditor=accept, case_path: Path = CASE) -> Kernel:
    case = load_case(case_path)
    return Kernel(fake, ROW, case, artifacts=ArtifactStore(tmp_path / "artifacts"), auditor=auditor, run_id="run1")


class PostFramework(Pytest):
    def post_command(self, role, target_file):
        from corsair.frameworks.base import PostCommand

        return PostCommand(("render-coverage", role, target_file), {"HOME": "/tmp", "POST_ONLY": "1"})


class PostSandboxes(FakeSandboxes):
    def __init__(self, post_result=Exec(0, b"rendered report\n", b"renderer warning\n"), *, clock=None):
        super().__init__(dict(HAPPY))
        self.post_result = post_result
        self.clock = clock

    def exec_once(self, name, argv, *, workdir, env=None, timeout=None):
        if argv[0] == "render-coverage":
            self.execs.append((name, tuple(argv)))
            self.exec_environments.append(dict(env or {}))
            if self.clock is not None:
                self.clock[0] = 14.0
            if isinstance(self.post_result, Exception):
                raise self.post_result
            return self.post_result
        result = super().exec_once(name, argv, workdir=workdir, env=env, timeout=timeout)
        if "pytest" in argv and self.clock is not None:
            self.clock[0] = 11.0
        return result


def test_post_command_environment_is_an_immutable_snapshot():
    from corsair.frameworks.base import PostCommand

    environment = {"HOME": "/tmp"}
    command = PostCommand(("render-coverage",), environment)
    environment["COVERAGE_PROCESS_START"] = "/work/coverage.rc"

    assert dict(command.environment) == {"HOME": "/tmp"}
    with pytest.raises(TypeError):
        command.environment["COVERAGE_PROCESS_START"] = "/work/coverage.rc"


def test_post_command_uses_its_own_environment_and_records_the_whole_invocation(tmp_path, monkeypatch):
    clock = [10.0]
    monkeypatch.setattr("corsair.kernel.time.monotonic", lambda: clock[0])
    fake = PostSandboxes(clock=clock)
    k = kernel(fake, tmp_path)
    k.framework = PostFramework()

    run = k.run_probe("image", REFERENCE, "vulnerable", "control")

    assert run.result is RoleResult.PASS
    assert [argv[0] for _, argv in fake.execs] == ["mkdir", "python", "render-coverage"]
    assert fake.execs[-1][1] == ("render-coverage", "control", "documents.py")
    assert fake.exec_environments[-1] == {"HOME": "/tmp", "POST_ONLY": "1"}
    assert fake.exec_environments[-2]["COVERAGE_FILE"] == "/tmp/corsair/coverage"
    output = k.artifacts.get(run.output)
    assert b"$ render-coverage control documents.py" in output
    assert b"1 passed" in output and b"rendered report" in output and b"renderer warning" in output
    assert run.duration_s == 4.0
    assert run.cleanup_confirmed is True and fake.labelled() == []


@pytest.mark.parametrize(("post_result", "expected", "message"), [
    (Exec(2, b"partial report\n", b"render failed\n"), RoleResult.ERROR, "exited 2"),
    (Exec(None, b"partial report\n", b"", timed_out=True), RoleResult.INFRA, "timed out"),
    (Exec(None, b"partial report\n", b"", output_limited=True), RoleResult.INFRA, "output limit"),
    (Exec(None, b"partial report\n", b"", container_failed=True), RoleResult.INFRA, "container failed"),
    (RuntimeError("renderer control failure"), RoleResult.INFRA, "renderer control failure"),
])
def test_post_command_failure_rejects_even_complete_primary_reports(tmp_path, post_result, expected, message):
    fake = PostSandboxes(post_result)
    k = kernel(fake, tmp_path)
    k.framework = PostFramework()

    run = k.run_probe("image", REFERENCE, "vulnerable", "control")

    assert run.result is expected
    assert run.invariant_held is None and run.covered_target is None
    assert run.junit_tests == 0 and run.junit is None and run.coverage is None
    assert message in run.message
    assert fake.copied_results == []
    assert run.duration_s is not None
    assert run.cleanup_confirmed is True and fake.labelled() == []
    output = k.artifacts.get(run.output)
    assert b"$ render-coverage control documents.py" in output
    assert b"1 passed" in output
    if isinstance(post_result, Exec):
        assert b"partial report" in output


def test_no_post_command_keeps_the_direct_probe_result(tmp_path):
    class DirectFramework(Pytest):
        def post_command(self, role, target_file):
            return None

    fake = FakeSandboxes(dict(HAPPY))
    k = kernel(fake, tmp_path)
    k.framework = DirectFramework()

    run = k.run_probe("image", REFERENCE, "vulnerable", "control")

    assert run.result is RoleResult.PASS and run.covered_lines == (4,)
    assert [argv[0] for _, argv in fake.execs] == ["mkdir", "python"]
    assert run.cleanup_confirmed is True and fake.labelled() == []


# --- gate 1 -------------------------------------------------------------------------------------------------------


def test_ast_guard_requires_the_three_symbols_and_one_payload_argument():
    assert ast_guard(REFERENCE.probe).passed
    missing = ast_guard("CONTROL_PAYLOAD = 1\ndef run_target(p): pass\n")
    assert not missing.passed and "EXPLOIT_PAYLOAD" in missing.reason
    arity = ast_guard("CONTROL_PAYLOAD = 1\nEXPLOIT_PAYLOAD = 2\ndef run_target(p, q): pass\n")
    assert not arity.passed and "exactly one" in arity.reason
    broken = ast_guard("def (:\n")
    assert not broken.passed and broken.stage is Gate.AST_GUARD


@pytest.mark.parametrize("line", ["from unittest import mock", "import unittest.mock", "from unittest.mock import patch",
                                  "import pytest_mock", "import responses"])
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
    assert [(r.revision, r.role, r.result) for r in verdict.runs] == [
        ("vulnerable", "control", RoleResult.PASS), ("vulnerable", "exploit", RoleResult.PASS),
        ("fixed", "control", RoleResult.PASS), ("fixed", "exploit", RoleResult.FAIL)]
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


async def test_fixed_revision_uses_its_trusted_target_lines_without_changing_the_hypothesis(tmp_path):
    scenario = {
        **HAPPY,
        ("fixed", "control"): Script("holds", covered_lines=(7,)),
        ("fixed", "exploit"): Script("holds", covered_lines=(7,)),
    }
    fake = FakeSandboxes(scenario)
    case = load_case(CASE)
    evaluator = Kernel(fake, ROW, case, artifacts=ArtifactStore(tmp_path / "artifacts"), auditor=accept,
                       fixed_target_lines=(7,))

    evaluation = await evaluator.evaluate(REFERENCE)

    assert evaluation.gate.stage is Gate.VERIFIED
    assert evaluation.verdict is not None and evaluation.verdict.fix is Fix.VERIFIED
    assert [(run.revision, run.covered_lines) for run in evaluation.runs] == [
        ("vulnerable", (4,)), ("vulnerable", (4,)), ("fixed", (7,)), ("fixed", (7,))]
    assert evaluation.submission.hypothesis.target_lines == (4,)


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
    assert second.verdict is not None and len(fake.creates) == builds_before  # cache hit, no new build sandbox
    other = with_build.model_copy(update={"build_script": "pip install -e .[test]"})
    await k.evaluate(other)
    assert len(fake.creates) == builds_before + 2
    case = load_case(CASE)
    assert environment_key(ROW, case.revision.tree_sha256, "a") != environment_key(ROW, case.revision.tree_sha256, "b")


async def test_failed_build_returns_the_tail_and_runs_nothing(tmp_path):
    fake = FakeSandboxes(dict(HAPPY), build_exit={"vulnerable": 1})
    evaluation = await kernel(fake, tmp_path).evaluate(REFERENCE.model_copy(update={"build_script": "pip install x"}))
    assert not evaluation.gate.passed and evaluation.gate.stage is Gate.BUILD_REPLAY
    assert "no matching distribution" in evaluation.gate.stderr_tail
    assert evaluation.runs == () and fake.opened == []
    assert terminal_verdict(evaluation.gate, 1).label is Label.UNABLE_TO_RUN


async def test_build_output_overflow_is_infrastructure_not_a_build_diagnosis(tmp_path):
    from corsair.sandbox.port import Exec

    class NoisyBuild(FakeSandboxes):
        def exec_once(self, name, argv, *, workdir, env=None, timeout=None):
            if argv[0] == "bash" and argv[-1].endswith("build.sh"):
                return Exec(None, b"x" * 20, b"", output_limited=True)
            return super().exec_once(name, argv, workdir=workdir, env=env, timeout=timeout)

    evaluation = await kernel(NoisyBuild(dict(HAPPY)), tmp_path).evaluate(
        REFERENCE.model_copy(update={"build_script": "pip install x"}))
    assert evaluation.gate.stage is Gate.INFRA and "output limit" in evaluation.gate.reason
    assert terminal_verdict(evaluation.gate, 1).label is Label.ERROR


async def test_control_must_hold_before_the_exploit_runs(tmp_path):
    fake = FakeSandboxes({**HAPPY, ("vulnerable", "control"): Script("errored", "FileNotFoundError", "no such file")})
    evaluation = await kernel(fake, tmp_path).evaluate(REFERENCE)
    assert evaluation.gate.stage is Gate.CONTROL_RUN and "FileNotFoundError" in evaluation.gate.reason
    assert [r.role for r in evaluation.runs] == ["control"]
    assert terminal_verdict(evaluation.gate, 2).label is Label.INCONCLUSIVE


async def test_control_that_never_reaches_the_target_lines_is_rejected(tmp_path):
    fake = FakeSandboxes({**HAPPY, ("vulnerable", "control"): Script("holds", covered_lines=())})
    evaluation = await kernel(fake, tmp_path).evaluate(REFERENCE)
    assert evaluation.gate.stage is Gate.CONTROL_COVERAGE and "lines [4]" in evaluation.gate.reason


async def test_control_pass_exploit_fail_is_likely_not_exploitable(tmp_path):
    fake = FakeSandboxes({**HAPPY, ("vulnerable", "exploit"): Script("holds")})
    evaluation = await kernel(fake, tmp_path).evaluate(REFERENCE)
    assert evaluation.gate.passed
    assert evaluation.verdict.label is Label.LIKELY_NOT_EXPLOITABLE
    assert evaluation.verdict.rule == "K4"
    assert evaluation.verdict.revisions[0].label is Label.LIKELY_NOT_EXPLOITABLE
    assert evaluation.runs[1].result is RoleResult.FAIL
    assert evaluation.runs[1].invariant_held is True


async def test_exploit_crash_or_application_assertion_is_errored_not_violated(tmp_path):
    crash = FakeSandboxes({**HAPPY, ("vulnerable", "exploit"): Script("errored", "TypeError", "bad arg")})
    evaluation = await kernel(crash, tmp_path).evaluate(REFERENCE)
    assert evaluation.gate.stage is Gate.EXPLOIT_RUN and "TypeError" in evaluation.gate.reason
    app_assert = FakeSandboxes({**HAPPY, ("vulnerable", "exploit"): Script("violated", "AssertionError", "app", invariant_failed=False)})
    evaluation = await kernel(app_assert, tmp_path).evaluate(REFERENCE)
    assert evaluation.gate.stage is Gate.EXPLOIT_RUN and evaluation.runs[-1].result is RoleResult.ERROR


async def test_exploit_without_target_coverage_is_rejected(tmp_path):
    fake = FakeSandboxes({**HAPPY, ("vulnerable", "exploit"): Script("violated", "AssertionError", "x", covered_lines=())})
    evaluation = await kernel(fake, tmp_path).evaluate(REFERENCE)
    assert evaluation.gate.stage is Gate.EXPLOIT_COVERAGE


async def test_blind_audit_rejection_blocks_the_verdict_after_the_deterministic_gates(tmp_path):
    async def reject(submission: Submission) -> AuditResult:
        return AuditResult(valid=False, reason="run_target branches on the payload")

    fake = FakeSandboxes(dict(HAPPY))
    evaluation = await kernel(fake, tmp_path, auditor=reject).evaluate(REFERENCE)
    assert evaluation.gate.stage is Gate.BLIND_AUDIT and "branches" in evaluation.gate.reason
    assert evaluation.verdict.label is Label.INCONCLUSIVE and evaluation.verdict.rule == "K3"
    assert len(evaluation.runs) == 2  # the fixed revision never ran


async def test_fix_not_verified_when_the_exploit_still_violates_on_the_fixed_revision(tmp_path):
    fake = FakeSandboxes({**HAPPY, ("fixed", "exploit"): Script("violated", "AssertionError", "still")})
    evaluation = await kernel(fake, tmp_path, auditor=accept).evaluate(REFERENCE)
    assert evaluation.verdict is not None and evaluation.verdict.label is Label.LIKELY_EXPLOITABLE
    assert evaluation.verdict.fix is Fix.NOT_VERIFIED and "still violates" in evaluation.verdict.fix_reason


async def test_fixed_build_failure_leaves_the_finding_and_marks_the_fix_unverified(tmp_path):
    fake = FakeSandboxes(dict(HAPPY), build_exit={"fixed": 1})
    evaluation = await kernel(fake, tmp_path).evaluate(REFERENCE.model_copy(update={"build_script": "pip install ."}))
    assert evaluation.verdict is not None and evaluation.verdict.label is Label.LIKELY_EXPLOITABLE
    assert evaluation.verdict.fix is Fix.NOT_VERIFIED and "did not build" in evaluation.verdict.fix_reason


async def test_collection_failure_is_not_run_and_timeout_is_infra(tmp_path):
    not_run = FakeSandboxes({**HAPPY, ("vulnerable", "control"): Script("not_run")})
    evaluation = await kernel(not_run, tmp_path).evaluate(REFERENCE)
    assert evaluation.gate.stage is Gate.CONTROL_RUN and evaluation.runs[0].result is RoleResult.NOT_RUN
    timeout = FakeSandboxes({**HAPPY, ("vulnerable", "exploit"): Script("timeout")})
    evaluation = await kernel(timeout, tmp_path).evaluate(REFERENCE)
    assert evaluation.gate.stage is Gate.INFRA and evaluation.runs[-1].result is RoleResult.INFRA
    assert terminal_verdict(evaluation.gate, 1).label is Label.ERROR
    assert evaluation.verdict is not None
    assert evaluation.verdict.label is Label.ERROR and evaluation.verdict.rule == "K0"
    assert evaluation.verdict.fix is Fix.NOT_VERIFIED
    assert evaluation.verdict.runs == evaluation.runs
    assert evaluation.verdict.revisions[0].label is Label.ERROR
    assert evaluation.verdict.revisions[0].rule == "K0"


async def test_native_report_and_driver_record_must_agree(tmp_path):
    fake = FakeSandboxes({**HAPPY, ("vulnerable", "control"): Script("holds", junit_disagrees=True)})
    evaluation = await kernel(fake, tmp_path).evaluate(REFERENCE)
    assert evaluation.runs[0].result is RoleResult.ERROR and "disagrees" in (evaluation.runs[0].message or "")


async def test_held_sandbox_identity_is_never_reused_or_removed(tmp_path):
    fake = FakeSandboxes(dict(HAPPY))
    k = kernel(fake, tmp_path)
    from corsair.sandbox.port import SandboxSpec, labels
    held = SandboxSpec(image=ROW.image, workdir="/work", labels=labels("run1", "build", revision="vulnerable",
                                                                       env=environment_key(ROW, k.case.revision.tree_sha256, "",
                                                                                           runtime_image_id=k.runtime_image_id)[:16])).name
    fake.held.add(held)
    evaluation = await k.evaluate(REFERENCE)
    assert evaluation.gate.stage is Gate.INFRA and "SandboxExists" in evaluation.gate.reason
    assert held not in fake.removed


def test_no_runtime_row_and_no_submission_terminal_verdicts():
    assert terminal_verdict(None, 0).label is Label.ERROR


def test_submission_digest_is_stable_and_hypothesis_lines_are_sorted_unique():
    assert REFERENCE.sha256 == Submission.model_validate_json(json.dumps(REFERENCE.model_dump(mode="json"))).sha256
    hypothesis = Hypothesis(target_file="a.py", target_symbol="f", target_lines=(9, 3, 3), root_cause="x", expected_violation="y")
    assert hypothesis.target_lines == (3, 9)
    with pytest.raises(ValueError):
        Hypothesis(target_file="/abs.py", target_symbol="f", target_lines=(1,), root_cause="x", expected_violation="y")


def test_environment_cache_binds_the_framework_and_resolved_runtime_image():
    tree = load_case(CASE).revision.tree_sha256
    assert environment_key(ROW, tree, "") != environment_key(ROW.model_copy(update={"framework": "node-test"}), tree, "")
    assert environment_key(ROW, tree, "", runtime_image_id="sha256:first") != environment_key(
        ROW, tree, "", runtime_image_id="sha256:second")


async def test_fixed_exploit_raising_a_non_assertion_keeps_the_label_but_asks_for_a_fix_correction(tmp_path):
    fake = FakeSandboxes({**HAPPY, ("fixed", "exploit"): Script("errored", "ValueError", "not in the subpath")})
    evaluation = await kernel(fake, tmp_path, auditor=accept).evaluate(REFERENCE)
    assert evaluation.gate.stage is Gate.FIX_RUN and not evaluation.gate.passed
    assert "ValueError" in evaluation.gate.reason and "catch it inside run_target" in evaluation.gate.reason
    assert evaluation.verdict is not None and evaluation.verdict.label is Label.LIKELY_EXPLOITABLE
    assert evaluation.verdict.fix is Fix.NOT_VERIFIED
    assert evaluation.submission == REFERENCE


async def test_hypothesis_must_target_the_reported_file_and_an_absent_target_is_decided_without_a_sandbox(tmp_path):
    fake = FakeSandboxes(dict(HAPPY))
    k = kernel(fake, tmp_path)
    other = REFERENCE.model_copy(update={"hypothesis": REFERENCE.hypothesis.model_copy(update={"target_file": "other.py"})})
    evaluation = await k.evaluate(other)
    assert evaluation.gate.stage is Gate.TARGET_BINDING and "reports documents.py" in evaluation.gate.reason
    assert fake.creates == [] and evaluation.runs == ()
    assert reported_target_present(k.case) is None
    missing = k.case.model_copy(update={"finding": k.case.finding.model_copy(update={"file_path": "maintenance/logs.py"})})
    assert "does not exist" in (reported_target_present(missing) or "")
    unnamed = k.case.model_copy(update={"finding": k.case.finding.model_copy(update={"file_path": None})})
    assert target_binding(unnamed, REFERENCE.hypothesis).passed
    assert not target_binding(unnamed, other.hypothesis).passed  # other.py is not in the tree either


async def test_symbol_and_lines_must_exist_in_the_target_file(tmp_path):
    fake = FakeSandboxes(dict(HAPPY))
    k = kernel(fake, tmp_path)
    wrong_symbol = REFERENCE.model_copy(update={"hypothesis": REFERENCE.hypothesis.model_copy(update={"target_symbol": "rotate_logs"})})
    evaluation = await k.evaluate(wrong_symbol)
    assert evaluation.gate.stage is Gate.TARGET_BINDING and "does not appear" in evaluation.gate.reason
    far = REFERENCE.model_copy(update={"hypothesis": REFERENCE.hypothesis.model_copy(update={"target_lines": (4, 400)})})
    evaluation = await k.evaluate(far)
    assert evaluation.gate.stage is Gate.TARGET_BINDING and "out of range" in evaluation.gate.reason
    assert fake.creates == []


@pytest.mark.parametrize(("role", "invariant_held", "expected"), [
    ("control", True, "PASS"), ("control", False, "FAIL"),
    ("exploit", False, "PASS"), ("exploit", True, "FAIL"),
])
def test_role_result_maps_boolean_invariant_to_role_expectation(role, invariant_held, expected):
    assert role_result(role, invariant_held).value == expected


@pytest.mark.parametrize("value", [None, 0, 1, "false", {}, []])
def test_role_result_rejects_non_boolean_invariants(value):
    with pytest.raises(TypeError):
        role_result("exploit", value)


async def test_both_roles_pass_is_likely_exploitable(tmp_path):
    result = await kernel(FakeSandboxes(dict(HAPPY)), tmp_path).evaluate(REFERENCE)
    assert result.verdict.label is Label.LIKELY_EXPLOITABLE
    assert result.verdict.rule == "K1"
    assert isinstance(result.verdict.revisions[0], RevisionDisposition)
    assert [run.result for run in result.runs[:2]] == [RoleResult.PASS, RoleResult.PASS]
    assert [run.invariant_held for run in result.runs[:2]] == [True, False]


async def test_control_false_is_inconclusive(tmp_path):
    fake = FakeSandboxes({**HAPPY, ("vulnerable", "control"): Script("violated", "AssertionError", "control false")})
    result = await kernel(fake, tmp_path).evaluate(REFERENCE)
    assert result.verdict.label is Label.INCONCLUSIVE and result.verdict.rule == "K3"
    assert [run.role for run in result.runs] == ["control", "exploit"]
    assert result.runs[0].result is RoleResult.FAIL


async def test_audit_rejection_blocks_negative_disposition(tmp_path):
    async def reject(submission):
        assert submission == REFERENCE  # no outcomes enter the blind auditor
        return AuditResult(valid=False, reason="unfair invariant")

    fake = FakeSandboxes({**HAPPY, ("vulnerable", "exploit"): Script("holds")})
    result = await kernel(fake, tmp_path, auditor=reject).evaluate(REFERENCE)
    assert result.gate.stage is Gate.BLIND_AUDIT
    assert result.verdict.label is Label.INCONCLUSIVE and result.verdict.rule == "K3"
    assert len(result.runs) == 2


@pytest.mark.parametrize(("exploit", "label", "rule"), [
    (Script("errored", "ValueError", "bad"), Label.INCONCLUSIVE, "K3"),
    (Script("not_run"), Label.INCONCLUSIVE, "K3"),
    (Script("timeout"), Label.ERROR, "K0"),
])
async def test_exploit_error_never_becomes_negative(tmp_path, exploit, label, rule):
    result = await kernel(FakeSandboxes({**HAPPY, ("vulnerable", "exploit"): exploit}), tmp_path).evaluate(REFERENCE)
    assert result.verdict.label is label and result.verdict.rule == rule
    assert result.runs[-1].invariant_held is None


@pytest.mark.parametrize("outcome", ["holds", "violated"])
async def test_no_auditor_blocks_both_decisive_labels(tmp_path, outcome):
    fake = FakeSandboxes({**HAPPY, ("vulnerable", "exploit"): Script(outcome, "AssertionError" if outcome == "violated" else None)})
    result = await kernel(fake, tmp_path, auditor=None).evaluate(REFERENCE)
    assert result.verdict.label is Label.INCONCLUSIVE and result.verdict.rule == "K3"
    assert result.gate.stage is Gate.BLIND_AUDIT


async def test_secure_fixed_revision_has_negative_disposition_and_verified_fix(tmp_path):
    result = await kernel(FakeSandboxes(dict(HAPPY)), tmp_path).evaluate(REFERENCE)
    vulnerable, fixed = result.verdict.revisions
    assert vulnerable.revision == "vulnerable" and vulnerable.label is Label.LIKELY_EXPLOITABLE
    assert fixed.revision == "fixed" and fixed.label is Label.LIKELY_NOT_EXPLOITABLE and fixed.rule == "K4"
    assert result.verdict.label is vulnerable.label
    assert result.verdict.fix is Fix.VERIFIED


async def test_removed_fixed_target_is_accepted_but_not_verified(tmp_path):
    from corsair.case import revision

    fixed_tree = tmp_path / "removed-target"
    fixed_tree.mkdir()
    (fixed_tree / "README").write_text("target removed\n")
    fake = FakeSandboxes(dict(HAPPY))
    k = kernel(fake, tmp_path)
    k.case = k.case.model_copy(update={"fixed_revision": revision(fixed_tree)})
    result = await k.evaluate(REFERENCE)
    assert result.gate.passed
    assert result.verdict.label is Label.LIKELY_EXPLOITABLE
    assert result.verdict.fix is Fix.NOT_VERIFIED
    fixed = result.verdict.revisions[1]
    assert fixed.label is Label.INCONCLUSIVE and fixed.rule == "K3"
    assert fixed.reason_code == "TARGET_REMOVED"
    assert len(fake.creates) == 1 and len(result.runs) == 2
