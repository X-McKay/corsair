"""Regressions at the native evidence boundary; no model or container required."""
import json

import pytest

from corsair.frameworks import framework
from corsair.frameworks.pytest_ import read_coverage
from corsair.kernel import Fix, Gate, RoleResult, ast_guard
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
    record = {"role": "exploit", "result": "PASS", "invariant_held": False,
              "exception_type": None, "message": None}
    case = '<testcase name="test_probe[exploit]"/>'
    if change == "skipped":
        case = '<testcase name="test_probe[exploit]"><skipped/></testcase>'
    elif change == "extra-test":
        case += '<testcase name="extra"/>'
    elif change == "wrong-test":
        case = case.replace('test_probe[exploit]', 'some_other_test')
    elif change == "wrong-role":
        record["role"] = "control"
    elif change == "application-assertion":
        record["exception_type"] = "AssertionError"
    files = {f"{RESULT_DIR}/junit.xml": f"<testsuites><testsuite>{case}</testsuite></testsuites>".encode(),
             f"{RESULT_DIR}/result.json": b"{" if change == "bad-json" else json.dumps(record).encode()}
    result = framework("pytest").read(files, REFERENCE.hypothesis, "exploit")
    assert result.result is RoleResult.ERROR


@pytest.mark.anyio
async def test_process_exit_must_agree_with_native_evidence(tmp_path):
    from corsair.sandbox.port import Exec

    class WrongExit(FakeSandboxes):
        def _probe(self, name):
            result = super()._probe(name)
            return Exec(7, result.stdout, result.stderr)

    result = await kernel(WrongExit(dict(HAPPY)), tmp_path).evaluate(REFERENCE)
    assert result.gate.stage is Gate.CONTROL_RUN
    assert result.runs[0].result is RoleResult.ERROR


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


@pytest.mark.anyio
@pytest.mark.parametrize("revision", ["vulnerable", "fixed"])
@pytest.mark.parametrize("role", ["control", "exploit"])
async def test_held_record_with_invariant_failure_is_error_and_cannot_verify_fix(tmp_path, revision, role):
    from corsair.kernel import RESULT_DIR, Label, RoleResult

    class ContradictoryHeldRecord(FakeSandboxes):
        def _probe(self, name):
            result = super()._probe(name)
            if (self._labels[name]["corsair.lite.revision"], self._env[name]["CORSAIR_ROLE"]) == (revision, role):
                path = f"{RESULT_DIR}/result.json"
                record = json.loads(self._files[name][path])
                record["invariant_failed"] = True
                self._files[name][path] = json.dumps(record).encode()
            return result

    fake = ContradictoryHeldRecord({**HAPPY, (revision, role): Script("holds")})
    evaluation = await kernel(fake, tmp_path).evaluate(REFERENCE)
    run = next(run for run in evaluation.runs if (run.revision, run.role) == (revision, role))
    assert run.result is RoleResult.ERROR and run.invariant_held is None
    assert "invariant_failed" in run.message
    disposition = next(item for item in evaluation.verdict.revisions if item.revision == revision)
    assert disposition.label is Label.INCONCLUSIVE and disposition.rule == "K3"
    assert evaluation.verdict.fix is Fix.NOT_VERIFIED


@pytest.mark.parametrize("adapter_name", ["pytest", "node-test", "javac-java", "perl-tap"])
@pytest.mark.parametrize("role,result,held,native,exception", [
    ("control", "PASS", True, "", None),
    ("exploit", "PASS", False, "", None),
    ("control", "FAIL", False, '<failure message="role mismatch"/>', None),
    ("exploit", "FAIL", True, '<failure message="role mismatch"/>', None),
    ("exploit", "ERROR", None, "native-error", "ValueError"),
])
def test_adapter_reads_boolean_role_results(tmp_path, adapter_name, role, result, held, native, exception):
    from corsair.kernel import RoleResult

    record = dict(role=role, result=result, invariant_held=held, exception_type=exception, message=None)
    if native == "native-error":
        native = ('<failure message="application"/>' if adapter_name in ("pytest", "node-test")
                  else '<error message="application"/>')
    target = "Documents.java" if adapter_name == "javac-java" else "documents.py"
    hypothesis = REFERENCE.hypothesis.model_copy(update={"target_file": target})
    (tmp_path / target).write_text("class Documents {}\n")
    files = {"/tmp/corsair/result.json": json.dumps(record).encode(),
             "/tmp/corsair/junit.xml": f'<testsuite><testcase name="test_probe[{role}]">{native}</testcase></testsuite>'.encode(),
             "/tmp/corsair/coverage.json": json.dumps({"files": {f"/work/{target}": {"executed_lines": [4]}}}).encode(),
             "/tmp/corsair/jacoco.xml": (f'<report><package name=""><sourcefile name="{target}">'
                                         '<line nr="4" ci="1"/></sourcefile></package></report>').encode()}
    read = framework(adapter_name).read(files, hypothesis, role, tmp_path)
    assert read.result is RoleResult(result)
    assert read.invariant_held is held
    assert read.covered_lines == (4,)


@pytest.mark.parametrize("change", ["old-holds", "old-violated", "wrong-role", "not-bool", "missing-result",
                                    "missing-boolean", "result-polarity", "native-failure", "native-error",
                                    "extra-test", "exception-on-pass", "boolean-on-error", "no-exception-on-error",
                                    "two-native-problems"])
@pytest.mark.parametrize("adapter_name", ["pytest", "node-test", "javac-java", "perl-tap"])
def test_new_record_rejects_stale_and_contradictory_evidence(tmp_path, adapter_name, change):
    from corsair.kernel import RoleResult

    record = dict(role="exploit", result="PASS", invariant_held=False, exception_type=None, message=None)
    native = '<testcase name="test_probe[exploit]"/>'
    if change.startswith("old-"):
        outcome = change.removeprefix("old-")
        record = dict(role="exploit", outcome=outcome, invariant_failed=outcome == "violated",
                      exception_type="AssertionError" if outcome == "violated" else None, message=None)
    elif change == "wrong-role":
        record["role"] = "control"
    elif change == "not-bool":
        record["invariant_held"] = "false"
    elif change == "missing-result":
        del record["result"]
    elif change == "missing-boolean":
        del record["invariant_held"]
    elif change == "result-polarity":
        record["invariant_held"] = True
    elif change == "native-failure":
        native = '<testcase name="test_probe[exploit]"><failure/></testcase>'
    elif change == "native-error":
        record.update(result="FAIL", invariant_held=True)
        native = '<testcase name="test_probe[exploit]"><error/></testcase>'
    elif change == "extra-test":
        native += native
    elif change == "exception-on-pass":
        record["exception_type"] = "AssertionError"
    elif change == "boolean-on-error":
        record.update(result="ERROR", exception_type="AssertionError")
        native = '<testcase name="test_probe[exploit]"><error/></testcase>'
    elif change == "no-exception-on-error":
        record.update(result="ERROR", invariant_held=None)
        native = '<testcase name="test_probe[exploit]"><error/></testcase>'
    else:
        record.update(result="FAIL", invariant_held=True)
        native = '<testcase name="test_probe[exploit]"><failure/><error/></testcase>'
    read = framework(adapter_name).read({"/tmp/corsair/result.json": json.dumps(record).encode(),
                       "/tmp/corsair/junit.xml": f'<testsuite>{native}</testsuite>'.encode()},
                      REFERENCE.hypothesis, "exploit", tmp_path)
    assert read.result is RoleResult.ERROR
    assert read.invariant_held is None


@pytest.mark.anyio
async def test_public_run_records_use_only_boolean_role_results(tmp_path):
    result = await kernel(FakeSandboxes(dict(HAPPY)), tmp_path).evaluate(REFERENCE)
    for run in json.loads(result.model_dump_json())["runs"]:
        assert "outcome" not in run
        assert run["result"] in {"PASS", "FAIL", "ERROR", "NOT_RUN", "INFRA"}
        assert isinstance(run["invariant_held"], bool)


@pytest.mark.anyio
async def test_long_error_with_exit_disagreement_stays_error(tmp_path):
    from corsair.sandbox.port import Exec

    class WrongExit(FakeSandboxes):
        def _probe(self, name):
            result = super()._probe(name)
            return Exec(7, result.stdout, result.stderr)

    fake = WrongExit({**HAPPY, ("vulnerable", "control"): Script("errored", "ValueError", "x" * 2000)})
    result = await kernel(fake, tmp_path).evaluate(REFERENCE)
    assert result.runs[0].result is RoleResult.ERROR
    assert result.runs[0].exception_type == "ValueError"
    assert len(result.runs[0].message) <= 2000


@pytest.mark.parametrize("adapter_name,wrong_tag", [
    ("pytest", "error"), ("node-test", "error"), ("javac-java", "failure"), ("perl-tap", "failure"),
])
def test_native_error_tag_must_match_the_runtime(tmp_path, adapter_name, wrong_tag):
    record = dict(role="exploit", result="ERROR", invariant_held=None, exception_type="ValueError", message="application")
    files = {"/tmp/corsair/result.json": json.dumps(record).encode(),
             "/tmp/corsair/junit.xml": (f'<testsuite><testcase name="test_probe[exploit]">'
                                        f'<{wrong_tag}/></testcase></testsuite>').encode()}
    result = framework(adapter_name).read(files, REFERENCE.hypothesis, "exploit", tmp_path)
    assert result.result is RoleResult.ERROR and result.invariant_held is None
    assert "disagrees" in result.message
