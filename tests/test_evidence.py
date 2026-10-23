"""Regressions at the native evidence boundary; no model or container required."""
import json

import pytest

from corsair.frameworks import framework
from corsair.frameworks.pytest_ import read_coverage
from corsair.kernel import Fix, Gate, Outcome, ast_guard
from tests.fakes import FakeSandboxes, Script
from tests.test_kernel import HAPPY, REFERENCE, kernel


@pytest.mark.parametrize("definition", [
    "def outer():\n    def run_target(payload): pass",
    "async def run_target(payload): pass",
    "def run_target(payload, **kwargs): pass",
    "def run_target(first, /, payload): pass",
])
def test_guard_rejects_a_driver_that_cannot_be_called_synchronously_with_one_payload(definition):
    assert not ast_guard(f"CONTROL_PAYLOAD=1\nEXPLOIT_PAYLOAD=2\n{definition}\n").passed


def test_coverage_must_name_the_exact_target_not_a_suffix_collision():
    report = {"files": {"/work/unrelated/documents.py": {"executed_lines": [4]}}}
    assert read_coverage(json.dumps(report).encode(), REFERENCE.hypothesis) == (False, ())


@pytest.mark.anyio
async def test_both_payloads_must_execute_every_declared_target_line(tmp_path):
    submission = REFERENCE.model_copy(update={"hypothesis": REFERENCE.hypothesis.model_copy(update={"target_lines": (3, 4)})})
    result = await kernel(FakeSandboxes(dict(HAPPY)), tmp_path).evaluate(submission)
    assert result.gate.stage is Gate.CONTROL_COVERAGE


@pytest.mark.anyio
@pytest.mark.parametrize("role", ["control", "exploit"])
@pytest.mark.parametrize("coverage", [False, None])
async def test_fix_requires_known_target_coverage_for_both_payloads(tmp_path, role, coverage):
    fake = FakeSandboxes({**HAPPY, ("fixed", role): Script("holds", covered_target=coverage)})
    result = await kernel(fake, tmp_path).evaluate(REFERENCE)
    assert result.verdict.fix is Fix.NOT_VERIFIED


@pytest.mark.parametrize("change", ["skipped", "extra-test", "wrong-test", "wrong-role", "application-assertion", "bad-json"])
def test_adapter_rejects_missing_or_contradictory_native_evidence(change):
    from corsair.kernel import RESULT_DIR
    record = {"role": "exploit", "outcome": "violated", "exception_type": "AssertionError",
              "message": "outside", "invariant_failed": True}
    case = '<testcase name="test_probe[exploit]"><failure message="outside"/></testcase>'
    if change == "skipped":
        case = '<testcase name="test_probe[exploit]"><skipped/></testcase>'
        record.update(outcome="holds", exception_type=None)
    elif change == "extra-test":
        case += '<testcase name="extra"/>'
    elif change == "wrong-test":
        case = case.replace('test_probe[exploit]', 'some_other_test')
    elif change == "wrong-role":
        record["role"] = "control"
    elif change == "application-assertion":
        record["invariant_failed"] = False
    files = {f"{RESULT_DIR}/junit.xml": f"<testsuites><testsuite>{case}</testsuite></testsuites>".encode(),
             f"{RESULT_DIR}/result.json": b"{" if change == "bad-json" else json.dumps(record).encode()}
    result = framework("pytest").read(files, REFERENCE.hypothesis, "exploit")
    assert result.outcome not in (Outcome.HOLDS, Outcome.VIOLATED)


@pytest.mark.anyio
async def test_process_exit_must_agree_with_native_evidence(tmp_path):
    from corsair.sandbox.port import Exec

    class WrongExit(FakeSandboxes):
        def _probe(self, name):
            result = super()._probe(name)
            return Exec(7, result.stdout, result.stderr)

    result = await kernel(WrongExit(dict(HAPPY)), tmp_path).evaluate(REFERENCE)
    assert result.gate.stage is Gate.CONTROL_RUN
    assert result.runs[0].outcome is Outcome.ERRORED


def test_reported_target_cannot_resolve_outside_the_source_tree(tmp_path):
    from corsair.case import Case, Finding, revision
    from corsair.kernel import reported_target_present, target_binding

    outside = tmp_path / "outside.py"
    outside.write_text("def read_document():\n    pass\n")
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "documents.py").symlink_to(outside)
    case = Case(case_id="link", finding=Finding(title="t", file_path="documents.py"), revision=revision(tree))
    assert reported_target_present(case) is not None
    assert not target_binding(case, REFERENCE.hypothesis).passed


@pytest.mark.anyio
@pytest.mark.parametrize("revision", ["vulnerable", "fixed"])
@pytest.mark.parametrize("outcome", ["holds", "violated"])
async def test_decisive_exploit_requires_every_target_line_on_each_revision(tmp_path, revision, outcome):
    from corsair.kernel import Label

    fake = FakeSandboxes({**HAPPY, (revision, "exploit"): Script(outcome, "AssertionError" if outcome == "violated" else None, covered_lines=())})
    result = await kernel(fake, tmp_path).evaluate(REFERENCE)
    disposition = next(item for item in result.verdict.revisions if item.revision == revision)
    assert disposition.label is Label.INCONCLUSIVE and disposition.rule == "K3"
    if revision == "fixed":
        assert result.verdict.fix is Fix.NOT_VERIFIED
