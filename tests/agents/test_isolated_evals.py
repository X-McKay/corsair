"""Host-only authoring eval (static runner, admission facts, live scoring) and the per-agent eval command."""

import json
from uuid import uuid4

import pytest
from pydantic_ai import models

from corsair.agents.source.contracts import SourceFile
from corsair.ports.test_runner import ApprovedPatch, PatchFile
from evals import run as eval_run
from evals.test_authoring.admission import admission_facts, no_process_or_network, quoted_literals
from evals.test_authoring.evaluate import FILES, ScriptedRun, ScriptedRunner, authoring_checks, dataset
from evals.test_authoring.static_runner import StaticRunner

REFERENCE = FILES["reference"]
CONTROL, SECURITY = "test_documents.py::test_benign_control", "test_documents.py::test_security_rejects_outside_read"
SOURCE = (SourceFile(path="documents.py", content="def read_document(root, filename):\n    return ''\n"),)


@pytest.fixture(autouse=True)
def no_real_requests():
    with models.override_allow_model_requests(False):
        yield


def observe(content: str, path="test_documents.py", source=SOURCE):
    patch = ApprovedPatch(files=(PatchFile(path, content.encode()),), approved_paths=(path,))
    return StaticRunner(source).run(patch, control_test_id=CONTROL, security_test_id=SECURITY,
                                    discovery_command=("python", "-m", "pytest", "--collect-only", "-q"), operation=uuid4())


def test_static_runner_discovers_the_reference_pair_and_marks_execution_simulated():
    observed = observe(REFERENCE)
    assert observed.failure_layer is None and set(observed.discovery.test_ids) == {CONTROL, SECURITY}
    assert observed.execution.command == ("static-host-runner", "not-executed")
    assert [case.outcome for case in observed.execution.cases] == ["passed", "failed"]


@pytest.mark.parametrize("content, error", [
    ("def test_benign_control(:\n    pass\n", "SyntaxError"),
    (REFERENCE.replace("import documents", "import documents\nimport hallucinated_helper"), "No module named 'hallucinated_helper'"),
    (REFERENCE.replace("def test_benign_control", "def check_benign_control"), "expected exactly"),
    (REFERENCE + "\n\ndef test_extra():\n    assert True\n", "expected exactly"),
])
def test_static_runner_reports_what_collection_would_refuse(content, error):
    observed = observe(content)
    assert observed.failure_layer == "discovery" and observed.execution is None
    assert error in observed.discovery.errors


def test_static_runner_refuses_files_it_cannot_analyse():
    with pytest.raises(ValueError, match="Python test files only"):
        observe("class SecurityTest {}", path="src/test/java/SecurityTest.java")


def test_scripted_runner_repeats_the_last_condition_and_delegates_static_runs():
    fake = ScriptedRunner((ScriptedRun(status="collection_error"), ScriptedRun(status="static")), StaticRunner(SOURCE))
    patch = ApprovedPatch(files=(PatchFile("test_documents.py", REFERENCE.encode()),), approved_paths=("test_documents.py",))
    layers = [fake.run(patch, control_test_id=CONTROL, security_test_id=SECURITY, discovery_command=("pytest",),
                       operation=uuid4()).failure_layer for _ in range(3)]
    assert layers == ["discovery", None, None] and fake.sources == ["injected", "static_simulated", "static_simulated"]


def test_admission_facts_place_the_planned_input_and_refuse_process_use():
    plan = next(c for c in dataset().cases if c.name == "reference_realization").inputs.inputs.plan
    files = {"test_documents.py": REFERENCE}
    assert quoted_literals(plan.security.input) == {"../outside.txt"}
    assert all(admission_facts(plan, files, (64, 65, 66)).values())
    swapped = REFERENCE.replace('"../outside.txt"', '"document.txt"').replace(
        'read_document(allowed, "document.txt")\n    events', 'read_document(allowed, "../outside.txt")\n    events', 1)
    facts = admission_facts(plan, {"test_documents.py": swapped}, (64, 65, 66))
    assert not facts["planned_input_in_security"] and not facts["planned_input_not_in_control"]
    assert not admission_facts(plan, files, (48,))["planned_failure_is_assert"]
    assert not no_process_or_network("import subprocess\n") and not no_process_or_network("import os\nos.system('x')\n")
    assert not no_process_or_network("from os import system\nsystem('echo x')\n")
    assert not no_process_or_network("import os as operating_system\noperating_system.system('echo x')\n")
    assert no_process_or_network("from os import path\nimport os as o\no.getcwd()\n")
    for dynamic in ("__import__('subprocess').run(['id'])\n", "import importlib\nimportlib.import_module('socket')\n",
                    "import os\ngetattr(os, 'system')('id')\n", "exec('import subprocess')\n"):
        assert not no_process_or_network(dynamic), dynamic
    assert no_process_or_network(REFERENCE)


def test_live_scoring_drops_only_the_scripted_authors_own_counts():
    c = next(c for c in dataset().cases if c.name == "reference_realization")
    from corsair.agents.test_authoring.contracts import TestPatch
    output = TestPatch.model_validate({
        "status": "patch", "files": [{"path": "test_documents.py", "content": REFERENCE}],
        "control_test_id": CONTROL, "security_test_id": SECURITY,
        "discovery_command": list(c.inputs.inputs.plan.discovery_command), "run_command": ["static-host-runner", "not-executed"],
        "patch_sha256": ApprovedPatch(files=(PatchFile("test_documents.py", REFERENCE.encode()),),
                                      approved_paths=("test_documents.py",)).sha256,
        "security_assertion_lines": [65], "limitations": ["host"],
        "dev_runs": [{"run": 1, "operation": "x", "status": "discovered", "discovered_test_ids": [CONTROL, SECURITY],
                      "errors": "", "control": {"outcome": "passed"}, "security": "withheld", "run_command": [],
                      "cleanup": "not_required",
                      "patch_sha256": ApprovedPatch(files=(PatchFile("test_documents.py", REFERENCE.encode()),),
                                                    approved_paths=("test_documents.py",)).sha256},
                     {"run": 2, "operation": "y", "status": "not_run", "discovered_test_ids": [], "errors": "budget",
                      "control": None, "security": None, "run_command": [], "cleanup": "not_required",
                      "patch_sha256": "0" * 64}]})
    scripted = authoring_checks(c.inputs.inputs, output, c.metadata)
    live = authoring_checks(c.inputs.inputs, output, c.metadata, live=True)
    assert not scripted["security_assertion_lines"] and "security_assertion_lines" not in live and "dev_runs" not in live
    assert all(live.values())


def test_eval_command_files_runs_and_compares_with_the_previous_and_promoted_runs(tmp_path, monkeypatch):
    assert eval_run.main(["authoring", "--results", str(tmp_path), "--note", "first"]) == 0
    first = json.loads((tmp_path / "authoring" / "index.jsonl").read_text().splitlines()[0])["run"]
    record = json.loads((tmp_path / "authoring" / first / "summary.json").read_text())
    assert record["summary"]["clean_attempts"] == record["summary"]["attempts"] == 20
    assert record["summary"]["identity"]["prompt_version"] and record["command"]["note"] == "first"
    assert "nothing to compare" in (tmp_path / "authoring" / first / "comparison.md").read_text()
    eval_run.main(["authoring", "--results", str(tmp_path), "--promote", first])
    second = record | {"run": "second"}
    second["summary"] = record["summary"] | {"clean_attempts": 11}
    text = eval_run.compare(second, record | {"reference_kind": "baseline"}, first)
    assert f"Compared with {first} (baseline)" in text and "clean attempts 20/20" in text
    assert eval_run.SUITES["environment"].module == "evals.environment.evaluate"


def test_author_witness_hooks_are_counted_as_a_score():
    from evals.test_authoring.admission import witness_hooks
    assert witness_hooks(REFERENCE) == 1 and witness_hooks("import sys\nsys.monitoring.use_tool_id(1, 'x')\n") == 1
    assert witness_hooks("def test_x():\n    assert 1 == 1\n") == 0


def test_chain_identity_carries_per_stage_versions_and_live_stages(tmp_path):
    def chain_run(planning_prompt, live):
        evidence = tmp_path / f"{planning_prompt}-{len(live)}"
        evidence.mkdir()
        (evidence / "configuration.json").write_text(json.dumps({
            "mode": "direct", "live_stages": live, "model": "scripted",
            "versions": {"planning": {"prompt_version": planning_prompt, "config_version": "c", "skill_sha256": "s"}}}))
        (evidence / "report.json").write_text(json.dumps({"cases": [], "failures": []}))
        return {"agent": "chain", "run": evidence.name, "summary": eval_run.summarize(evidence)}
    before, after = chain_run("test-planning-v6", []), chain_run("test-planning-v7", ["planning"])
    assert before["summary"]["identity"] != after["summary"]["identity"]
    text = eval_run.compare(after, before | {"reference_kind": "baseline"}, before["run"])
    assert "`versions`" in text and "test-planning-v7" in text and "`live_stages`" in text


@pytest.mark.parametrize("name", [
    "posix_spawn", "posix_spawnp", "spawnle", "spawnlp", "spawnlpe",
    "spawnve", "spawnvp", "spawnvpe", "execvp", "execvpe", "execle",
    "execlp", "execlpe", "forkpty",
])
@pytest.mark.parametrize("form", ["import os\nos.{name}('x')",
                                  "import os as o\no.{name}('x')",
                                  "from os import {name} as launch\nlaunch('x')",
                                  "import os\nlaunch = os.{name}"])
def test_listed_os_process_names_are_refused_in_supported_binding_forms(name, form):
    assert not no_process_or_network(form.format(name=name))


def test_deferred_literals_and_assertions_do_not_satisfy_plan_facts():
    plan = dataset().cases[0].inputs.inputs.plan
    content = ("def test_benign_control():\n    assert True\n\n"
               "def test_security_rejects_outside_read():\n"
               "    def never_called():\n        path = '../outside.txt'\n        assert False\n"
               "    actual = 1\n    assert actual == 1\n")
    facts = admission_facts(plan, {"test_documents.py": content}, (7,))
    assert not facts["planned_input_in_security"]
    assert not facts["planned_failure_is_assert"]


@pytest.mark.parametrize("control_body", [
    "    go = lambda: open('../outside.txt')\n    go()\n",
    "    def go():\n        return open('../outside.txt')\n    go()\n",
    "    def unused():\n        return open('../outside.txt')\n    assert True\n",
])
def test_adversarial_control_literals_remain_refused_inside_nested_scopes(control_body):
    # Parse only: none of this authored code executes on the host. Negative
    # control facts stay conservative even when call reachability is unknown.
    plan = dataset().cases[0].inputs.inputs.plan
    content = ("def test_benign_control():\n" + control_body
               + "\ndef test_security_rejects_outside_read():\n"
               "    path = '../outside.txt'\n    assert path\n")
    facts = admission_facts(plan, {"test_documents.py": content}, (len(content.splitlines()),))
    assert facts["planned_input_in_security"]
    assert facts["planned_failure_is_assert"]
    assert not facts["planned_input_not_in_control"]


def test_eval_command_offers_no_retired_planning_set():
    from evals.test_planning.evaluate import RETIRED
    assert not RETIRED & set(eval_run.SUITES["planning"].sets)


def test_authoring_eval_matches_unit_dependency_admission_and_retains_witness_boundary():
    from corsair.agents.test_planning.contracts import PlannedObservation

    witness_plan = next(c for c in dataset().cases if c.name == "reference_realization").inputs.inputs.plan
    observation = PlannedObservation(kind="dependency_call", property="Planned arguments reach the dependency",
                                     seam="Application-owned dependency reference", controlled_dependency="Recording mock")
    unit_plan = witness_plan.model_copy(update={
        "control": witness_plan.control.model_copy(update={"witness": None, "observation": observation}),
        "security": witness_plan.security.model_copy(update={"witness": None, "observation": observation}),
    })
    content = """from unittest.mock import Mock
import documents

def test_benign_control():
    dependency = Mock()
    documents.read_document(dependency, "document.txt")
    assert dependency.call_args.args == ("document.txt",)

def test_security_rejects_outside_read():
    dependency = Mock()
    documents.read_document(dependency, "../outside.txt")
    assert dependency.call_args.args == ("../outside.txt",)
"""
    files = {"test_documents.py": content}
    # Admission accepts the syntax; semantic validity remains a separate review.
    assert admission_facts(unit_plan, files, (13,))["stage_admitted"]
    assert not admission_facts(witness_plan, files, (13,))["stage_admitted"]
    files["test_documents.py"] += "\nimport sys\nsys.settrace(lambda *args: None)\n"
    assert not admission_facts(unit_plan, files, (13,))["stage_admitted"]
