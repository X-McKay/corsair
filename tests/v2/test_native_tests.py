from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from corsair.v2.contracts import (CommandResult, InvestigationPlan, ModelProfile, OperatorConfig,
                                  ProbeSpec, ReportSelector, SandboxProfile, SourceFile, SourceSnapshot,
                                  TestRecipe as NativeRecipe, WorkspaceLease)
from corsair.v2.native_tests import NativeTests
from corsair.v2.sandbox import Sandbox
from corsair.v2.storage import Store


IMAGE = "example.invalid/corsair/python@sha256:" + "b" * 64


# Golden reports model the actual aggregate documents emitted by Jest and Node's
# native --test TAP reporter. They are test data only; production always calls
# the OpenShell Sandbox boundary.
JEST_CROSS_FILE_GOLDEN = json.dumps({
    "numRuntimeErrorTestSuites": 0,
    "testResults": [
        {"name": "/workspace/probes/control.test.js", "assertionResults": [
            {"title": "control_probe", "ancestorTitles": ["control suite"], "status": "passed", "failureMessages": []}]},
        {"name": "/workspace/probes/security.test.js", "assertionResults": [
            {"title": "security_probe", "ancestorTitles": ["security suite"], "status": "failed",
             "failureMessages": ["Error: expect(true).toBe(false)\n    at security_probe (/workspace/probes/security.test.js:9:1)"]}]},
    ],
}).encode()

TAP_ASSERTION_GOLDEN = b"""TAP version 13
# Subtest: control_probe
ok 1 - control_probe
  ---
  duration_ms: 1.01
  ...
# Subtest: security_probe
not ok 2 - security_probe
  ---
  duration_ms: 2.02
  failureType: 'testCodeFailure'
  error: 'Expected values to be strictly equal'
  code: 'ERR_ASSERTION'
  name: 'AssertionError'
  stack: |-
    AssertionError [ERR_ASSERTION]: expected safe behavior
  ...
1..2
# tests 2
# pass 1
# fail 1
"""

TAP_NON_ASSERTION_ERROR_GOLDEN = TAP_ASSERTION_GOLDEN.replace(
    b"error: 'Expected values to be strictly equal'\n  code: 'ERR_ASSERTION'\n  name: 'AssertionError'\n  stack: |-\n    AssertionError [ERR_ASSERTION]: expected safe behavior",
    b"error: 'unexpected database error'\n  code: 'ERR_TEST_FAILURE'\n  name: 'Error'\n  stack: |-\n    Error: unexpected database error",
)
TAP_SKIPPED_GOLDEN = TAP_ASSERTION_GOLDEN.replace(
    b"not ok 2 - security_probe\n  ---\n  duration_ms: 2.02\n  failureType: 'testCodeFailure'\n  error: 'Expected values to be strictly equal'\n  code: 'ERR_ASSERTION'\n  name: 'AssertionError'\n  stack: |-\n    AssertionError [ERR_ASSERTION]: expected safe behavior\n  ...",
    b"ok 2 - security_probe # SKIP test fixture unavailable",
).replace(b"# fail 1", b"# fail 0")


def config(tmp_path: Path) -> OperatorConfig:
    policy = tmp_path / "policy.yaml"
    policy.write_text("version: 1\nnetwork_policies: {}\n")
    os.chmod(policy, 0o600)
    return OperatorConfig(storage_root=str(tmp_path / "store"), default_model=ModelProfile(model="test"),
                          sandbox=SandboxProfile(image=IMAGE, policy_path=str(policy), gateway="unit-registration",
                                                 workspace_root="/workspace"))


def plan() -> InvestigationPlan:
    control = ProbeSpec(role="control", path="probes/control_test.py", test_id="probes/control_test.py::test_control",
                        selector=ReportSelector(name="test_control", classname="probes.control_test"), objective="control",
                        input_description="ordinary input", expected_safe_behavior="works", citations=({"path": "app.py", "start_line": 1, "end_line": 1},))
    security = ProbeSpec(role="security", path="probes/security_test.py", test_id="probes/security_test.py::test_security",
                         selector=ReportSelector(name="test_security", classname="probes.security_test"), objective="security",
                         input_description="adversarial input", expected_safe_behavior="blocked", citations=({"path": "app.py", "start_line": 1, "end_line": 1},))
    recipe = NativeRecipe(report_format="junit", discovery_command=("discover",), execution_command=("execute",),
                          report_path=".corsair/report.xml")
    return InvestigationPlan(status="planned", summary="two probes", target_citations=({"path": "app.py", "start_line": 1, "end_line": 1},),
                             control=control, security=security, recipe=recipe)


def standard_plan(report_format: str) -> InvestigationPlan:
    control = ProbeSpec(role="control", path="probes/control.test.js", test_id="opaque-control-id",
                        selector=ReportSelector(name="control_probe", classname="control suite"), objective="control",
                        input_description="ordinary input", expected_safe_behavior="works", citations=({"path": "app.py", "start_line": 1, "end_line": 1},))
    security = ProbeSpec(role="security", path="probes/security.test.js", test_id="opaque-security-id",
                         selector=ReportSelector(name="security_probe", classname="security suite"), objective="security",
                         input_description="adversarial input", expected_safe_behavior="blocked", citations=({"path": "app.py", "start_line": 1, "end_line": 1},))
    recipe = NativeRecipe(report_format=report_format, discovery_command=("discover",), execution_command=("execute",),
                          report_path=".corsair/report.json")
    return InvestigationPlan(status="planned", summary="two probes", target_citations=({"path": "app.py", "start_line": 1, "end_line": 1},),
                             control=control, security=security, recipe=recipe)


def minitest_plan() -> InvestigationPlan:
    control = ProbeSpec(role="control", path="probes/control_test.rb", test_id="probes/control_test.rb::ControlProbe#test_control",
                        selector=ReportSelector(name="test_control", classname="ControlProbe"), objective="control",
                        input_description="ordinary input", expected_safe_behavior="works", citations=({"path": "app.py", "start_line": 1, "end_line": 1},))
    security = ProbeSpec(role="security", path="probes/security_test.rb", test_id="probes/security_test.rb::SecurityProbe#test_security",
                         selector=ReportSelector(name="test_security", classname="SecurityProbe"), objective="security",
                         input_description="adversarial input", expected_safe_behavior="blocked", citations=({"path": "app.py", "start_line": 1, "end_line": 1},))
    recipe = NativeRecipe(report_format="minitest-json", discovery_command=("discover",), execution_command=("execute",),
                          report_path=".corsair/report.json")
    return InvestigationPlan(status="planned", summary="two probes", target_citations=({"path": "app.py", "start_line": 1, "end_line": 1},),
                             control=control, security=security, recipe=recipe)


def snapshot(store: Store) -> SourceSnapshot:
    app = store.put(b"def app(): pass\n")
    value = {"schema_version": "source-v2", "repository": "fixture", "commit": None, "tree": None,
             "files": [{"path": "app.py", "artifact": app.model_dump(mode="json"), "mode": "100644"}], "skipped": []}
    manifest = store.put_json(value)
    return SourceSnapshot(repository="fixture", files=(SourceFile(path="app.py", artifact=app),), manifest=manifest)


def command(store: Store, operation: str, stdout: bytes, *, exit_code: int = 0) -> CommandResult:
    return CommandResult(operation_id=operation, sandbox_id="native-id", status="completed", exit_code=exit_code,
                         stdout=stdout.decode("utf-8", "replace"), stdout_ref=store.put(stdout), stderr_ref=store.put(b""),
                         duration_seconds=0.01)


def fake_sandbox(store: Store, commands: list[CommandResult], report: bytes):
    # A test double is confined to this unit test; the production NativeTests
    # constructor accepts only the real Sandbox boundary and has no fallback.
    sandbox = object.__new__(Sandbox)
    lease = WorkspaceLease(name="corsair-run-g1-123", sandbox_id="native-id", run_id="run", generation=1,
                           image=IMAGE, policy_sha256="c" * 64)
    sandbox.acquire_calls = sandbox.stage_calls = sandbox.release_calls = 0
    sandbox.command_calls = []
    sandbox.profile_identity = lambda: {"policy_sha256": "c" * 64}

    def acquire(run_id, generation, source_manifest):
        sandbox.acquire_calls += 1
        return lease

    def stage(received, source, overlays):
        sandbox.stage_calls += 1
        return {"status": "completed"}

    def execute(received, argv, operation_id, workdir=None):
        sandbox.command_calls.append(argv)
        return commands.pop(0)

    def release(received):
        sandbox.release_calls += 1
        return "confirmed"

    sandbox.acquire, sandbox.stage, sandbox.execute = acquire, stage, execute
    sandbox.read_predeclared_report = lambda received, path, max_bytes: report
    sandbox.release = release
    return sandbox


def pair() -> dict[str, str]:
    return {"probes/control_test.py": "def test_control(): pass\n",
            "probes/security_test.py": "def test_security(): pass\n"}


def standard_pair(native_plan: InvestigationPlan) -> dict[str, str]:
    return {native_plan.control.path: "test('control', () => {})\n",
            native_plan.security.path: "test('security', () => {})\n"}


def test_native_execution_admits_exact_junit_pair_and_assertion_failure(tmp_path):
    with Store(tmp_path / "store") as store:
        expected = ("probes/control_test.py::test_control\nprobes/security_test.py::test_security\n").encode()
        report = b"""<testsuite><testcase classname='probes.control_test' name='test_control'/><testcase classname='probes.security_test' name='test_security'><failure message='assertion failed'>AssertionError</failure></testcase></testsuite>"""
        sandbox = fake_sandbox(store, [command(store, "discovery", expected), command(store, "execution", b"", exit_code=1)], report)
        result = NativeTests(config(tmp_path), store, sandbox).execute(snapshot(store), plan(), pair(), "run")
        assert result.execution_status == "completed"
        assert result.cleanup == "confirmed"
        assert result.discovery_ok is True
        assert [item.outcome for item in result.observations] == ["passed", "failed"]
        assert result.observations[1].failure_type == "assertion"
        assert result.report_ref is not None


def test_cross_file_jest_golden_uses_selectors_not_test_id_grammar(tmp_path):
    with Store(tmp_path / "store") as store:
        native_plan = standard_plan("jest")
        discovered = b"opaque-control-id\nopaque-security-id\n"
        sandbox = fake_sandbox(store, [command(store, "discovery", discovered), command(store, "execution", b"", exit_code=1)],
                               JEST_CROSS_FILE_GOLDEN)
        result = NativeTests(config(tmp_path), store, sandbox).execute(snapshot(store), native_plan, standard_pair(native_plan), "run")
        assert result.execution_status == "completed"
        assert [item.test_id for item in result.observations] == ["opaque-control-id", "opaque-security-id"]
        assert [item.outcome for item in result.observations] == ["passed", "failed"]
        assert result.observations[1].failure_type == "assertion"


@pytest.mark.parametrize("mutate", [
    lambda document: document["testResults"][1]["assertionResults"].append(document["testResults"][1]["assertionResults"][0].copy()),
    lambda document: document["testResults"].append({"name": "/workspace/probes/unexpected.test.js", "assertionResults": []}),
])
def test_cross_file_jest_duplicate_or_unexpected_report_is_refused(tmp_path, mutate):
    with Store(tmp_path / "store") as store:
        document = json.loads(JEST_CROSS_FILE_GOLDEN)
        mutate(document)
        with pytest.raises(ValueError):
            NativeTests(config(tmp_path), store, fake_sandbox(store, [], b""))._observations(
                json.dumps(document).encode(), standard_plan("jest"), 1)


def test_jest_discovery_extra_selector_is_strict_before_execution(tmp_path):
    with Store(tmp_path / "store") as store:
        native_plan = standard_plan("jest").model_copy(update={"recipe": standard_plan("jest").recipe.model_copy(update={"discovery_format": "jest-json"})})
        discovery = json.loads(JEST_CROSS_FILE_GOLDEN)
        for suite in discovery["testResults"]:
            for test in suite["assertionResults"]:
                test["status"], test["failureMessages"] = "pending", []
        discovery["testResults"][0]["assertionResults"].append(
            {"title": "unexpected_probe", "ancestorTitles": ["control suite"], "status": "pending", "failureMessages": []})
        sandbox = fake_sandbox(store, [command(store, "discovery", json.dumps(discovery).encode())], b"")
        result = NativeTests(config(tmp_path), store, sandbox).execute(snapshot(store), native_plan, standard_pair(native_plan), "run")
        assert result.execution_status == "blocked"
        assert result.discovery_ok is False
        assert sandbox.command_calls == [("discover",)]
        assert sandbox.release_calls == 1


def test_node_tap_aggregate_golden_admits_assertion_pair(tmp_path):
    with Store(tmp_path / "store") as store:
        observed = NativeTests(config(tmp_path), store, fake_sandbox(store, [], b""))._observations(
            TAP_ASSERTION_GOLDEN, standard_plan("tap"), 1)
        assert [item.outcome for item in observed] == ["passed", "failed"]
        assert observed[1].failure_type == "assertion"


@pytest.mark.parametrize("report", [
    TAP_ASSERTION_GOLDEN.replace(b"# Subtest: security_probe", b"# Subtest: control_probe"),
    TAP_ASSERTION_GOLDEN.replace(b"# Subtest: control_probe", b"Bail out! fixture abort\n# Subtest: control_probe"),
])
def test_node_tap_duplicate_or_bailout_is_refused(tmp_path, report):
    with Store(tmp_path / "store") as store:
        with pytest.raises(ValueError):
            NativeTests(config(tmp_path), store, fake_sandbox(store, [], b""))._observations(report, standard_plan("tap"), 1)


def test_node_tap_nonassertion_error_is_not_security_assertion(tmp_path):
    with Store(tmp_path / "store") as store:
        observed = NativeTests(config(tmp_path), store, fake_sandbox(store, [], b""))._observations(
            TAP_NON_ASSERTION_ERROR_GOLDEN, standard_plan("tap"), 1)
        assert observed[1].outcome == "failed"
        assert observed[1].failure_type == "other"


def test_node_tap_skipped_probe_is_preserved_not_confirmed(tmp_path):
    with Store(tmp_path / "store") as store:
        observed = NativeTests(config(tmp_path), store, fake_sandbox(store, [], b""))._observations(
            TAP_SKIPPED_GOLDEN, standard_plan("tap"), 0)
        assert [item.outcome for item in observed] == ["passed", "skipped"]
        assert observed[1].failure_type is None


def test_cross_file_minitest_uses_reported_class_and_method_metadata(tmp_path):
    with Store(tmp_path / "store") as store:
        report = json.dumps({"schema": "corsair-minitest-v1", "tests": [
            {"class": "ControlProbe", "name": "test_control", "outcome": "passed", "failure": None},
            {"class": "SecurityProbe", "name": "test_security", "outcome": "failed", "failure": {
                "kind": "failure", "type": "Minitest::Assertion", "message": "Expected safe result", 
                "backtrace": ["/workspace/probes/security_test.rb:8:in `test_security'"]}},
        ]}).encode()
        observed = NativeTests(config(tmp_path), store, fake_sandbox(store, [], b""))._observations(report, minitest_plan(), 1)
        assert [item.outcome for item in observed] == ["passed", "failed"]
        assert observed[1].failure_type == "assertion"


def test_discovery_with_an_extra_id_blocks_before_execution(tmp_path):
    with Store(tmp_path / "store") as store:
        output = b"probes/control_test.py::test_control\nprobes/security_test.py::test_security\nextra\n"
        sandbox = fake_sandbox(store, [command(store, "discovery", output)], b"")
        result = NativeTests(config(tmp_path), store, sandbox).execute(snapshot(store), plan(), pair(), "run")
        assert result.execution_status == "blocked"
        assert result.discovery_ok is False
        assert len(result.commands) == 1
        assert result.cleanup == "confirmed"


def test_report_path_collision_is_refused_before_acquire(tmp_path):
    with Store(tmp_path / "store") as store:
        bad = plan().model_copy(update={"recipe": plan().recipe.model_copy(update={"report_path": "app.py"})})
        sandbox = fake_sandbox(store, [], b"")
        result = NativeTests(config(tmp_path), store, sandbox).execute(snapshot(store), bad, pair(), "run")
        assert result.execution_status == "blocked"
        assert "collides" in result.detail
        assert sandbox.acquire_calls == 0


def test_invalid_probe_source_is_refused_before_acquire(tmp_path):
    with Store(tmp_path / "store") as store:
        sandbox = fake_sandbox(store, [], b"")
        invalid_pair = pair() | {"probes/control_test.py": "  "}
        result = NativeTests(config(tmp_path), store, sandbox).execute(snapshot(store), plan(), invalid_pair, "run")
        assert result.execution_status == "blocked"
        assert "Native probe source" in result.detail
        assert sandbox.acquire_calls == sandbox.stage_calls == sandbox.release_calls == 0


def test_stop_after_discovery_does_not_dispatch_execution_and_releases_once(tmp_path):
    with Store(tmp_path / "store") as store:
        stopped = {"value": False}
        discovery = b"probes/control_test.py::test_control\nprobes/security_test.py::test_security\n"
        sandbox = fake_sandbox(store, [command(store, "discovery", discovery), command(store, "execution", b"", exit_code=1)], b"")
        original_execute = sandbox.execute

        def stop_after_discovery(received, argv, operation_id, workdir=None):
            result = original_execute(received, argv, operation_id, workdir)
            if argv == ("discover",):
                stopped["value"] = True
            return result

        sandbox.execute = stop_after_discovery
        result = NativeTests(config(tmp_path), store, sandbox).execute(snapshot(store), plan(), pair(), "run",
                                                                         stop_requested=lambda: stopped["value"])
        assert result.execution_status == "blocked"
        assert result.detail == "operator_cancelled_at_command_boundary"
        assert result.discovery_ok is True
        assert sandbox.command_calls == [("discover",)]
        assert sandbox.release_calls == 1


def test_stop_after_stage_releases_once_without_command_dispatch(tmp_path):
    with Store(tmp_path / "store") as store:
        stopped = {"value": False}
        sandbox = fake_sandbox(store, [], b"")

        def stop_after_stage(received, source, overlays):
            sandbox.stage_calls += 1
            stopped["value"] = True
            return {"status": "completed"}

        sandbox.stage = stop_after_stage
        result = NativeTests(config(tmp_path), store, sandbox).execute(snapshot(store), plan(), pair(), "run",
                                                                         stop_requested=lambda: stopped["value"])
        assert result.execution_status == "blocked"
        assert result.detail == "operator_cancelled_at_command_boundary"
        assert sandbox.acquire_calls == sandbox.stage_calls == sandbox.release_calls == 1
        assert sandbox.command_calls == []
