"""Exercise the authoring stage's confinement, run budget, withheld outcome and provenance through native SDK calls."""

import asyncio
from dataclasses import replace
from hashlib import sha256

import pytest
from pydantic import ValidationError
from pydantic_ai import models
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import UsageLimits

from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.adapters.pytest_runner import PytestRunner, PytestRunnerConfig
from corsair.agents.test_authoring import (
    AuthoringBudget, AuthoringDependencies, BlockedAuthoring, TestAuthoringInput, TestPatch, authoring_prompt,
    create_test_authoring_agent,
)
from corsair.agents.test_authoring.admission import REVIEWED_SELF_OBSERVING, self_observation
from corsair.agents.test_authoring.skills import SKILL_TEXT
from corsair.agents.test_authoring.static import assertion_lines, static_checks
from corsair.ports.test_runner import NativeTestRun
from evals.fixture_e2e.reviewed import DISCOVER, PREFIX, ReviewedLocalExecution, ReviewedWorkspace
from evals.test_authoring.evaluate import (
    FILES, EvaluationBudget, ScriptedRun, ScriptedRunner, authoring_checks, dataset, evaluate, passed,
)

REFERENCE = FILES["reference"]
SECURITY = "test_documents.py::test_security_rejects_outside_read"
PATCH = {"status": "patch", "security_assertion_lines": [64, 65, 66], "limitations": ["Development runs only"]}


@pytest.fixture(autouse=True)
def no_real_requests():
    with models.override_allow_model_requests(False):
        yield


def case(name="reference_realization"):
    return next(c for c in dataset().cases if c.name == name)


def runner(*runs):
    return ScriptedRunner(tuple(ScriptedRun.model_validate(r) for r in runs or ({"status": "discovered"},)))


def run(agent, inputs, fake=None, budget=AuthoringBudget(), **kwargs):
    fake = fake or runner()
    result = agent.run_sync(authoring_prompt(inputs), deps=AuthoringDependencies(inputs, fake, budget),
                            usage_limits=UsageLimits(request_limit=12, tool_calls_limit=10), **kwargs)
    return result, fake


def write(content=REFERENCE, path="test_documents.py"):
    return ToolCallPart("write_test_file", {"path": path, "content": content})


RUN = ToolCallPart("run_tests", {})


ALL_TOOLS, READ_ONLY = ["read_source", "write_test_file", "run_tests"], ["read_source"]


def responding(steps, final=PATCH, seen=None, offered=None):
    async def respond(messages, info):
        assert "Write exactly the two planned tests" in info.instructions and SKILL_TEXT.strip() in info.instructions
        tools = [t.name for t in info.function_tools]
        assert tools in (ALL_TOOLS, READ_ONLY)
        if offered is not None:
            offered.append(tools)
        done = sum(isinstance(p, ToolReturnPart) for m in messages for p in m.parts)
        if seen is not None:
            seen[:] = [p.content for m in messages for p in m.parts if isinstance(p, ToolReturnPart) and p.tool_name == "run_tests"]
        if done < len(steps):
            step = steps[done]
            # Fresh ids per response unless a test pins them, as a real provider would issue.
            return ModelResponse(parts=[part if isinstance(step, tuple) else replace(part, tool_call_id=f"call-{done}")
                                        for part in (step if isinstance(step, tuple) else (step,))])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"result": final})])
    return FunctionModel(respond)


READS = [ToolCallPart("read_source", {"path": "documents.py"}), ToolCallPart("read_source", {"path": "test_existing.py"})]


def test_reference_patch_is_assembled_from_this_runs_writes_and_runs_without_labels_in_prompt():
    c = case()
    (result, fake) = run(create_test_authoring_agent(responding([*READS, write(), RUN])), c.inputs.inputs)
    patch = result.output
    assert isinstance(patch, TestPatch) and all(authoring_checks(c.inputs.inputs, patch, c.metadata).values())
    assert patch.files[0].content == REFERENCE and patch.dev_runs[0].security == "withheld"
    assert patch.patch_sha256 == fake.calls[0] and patch.security_assertion_lines == (64, 65, 66)
    prompt = authoring_prompt(c.inputs.inputs)
    assert c.inputs.fixture_id not in prompt and '"quote"' not in prompt
    for label in ("runner_runs", "security_assertion_lines", "reference_realization", "vulnerable", "fixed"):
        assert label not in prompt


@pytest.mark.parametrize("path", ["documents.py", "conftest.py", "../test_documents.py", "/tmp/test_documents.py"])
def test_writes_outside_approved_paths_end_the_run_before_any_execution(path):
    fake = runner()
    with pytest.raises(UnexpectedModelBehavior):
        run(create_test_authoring_agent(responding([write(path=path), RUN])), case().inputs.inputs, fake)
    assert fake.calls == []


@pytest.mark.parametrize("steps,final", [
    ([write()], PATCH),                                                           # never ran
    ([write("x = 1\n"), RUN, write()], PATCH),                                    # wrote after the final run
    ([write(), RUN], PATCH | {"security_assertion_lines": [3]}),                  # not an assertion line
    ([write(), RUN], PATCH | {"verdict": "reproduced"}),                          # verdict field
    ([write(REFERENCE.replace("def test_security_rejects_outside_read", "def test_other")), RUN], PATCH),
])
def test_finalizer_refuses_unverified_patches(steps, final):
    with pytest.raises(UnexpectedModelBehavior):
        run(create_test_authoring_agent(responding(steps, final), output_retries=0), case().inputs.inputs)


@pytest.mark.parametrize("observed", [{"status": "collection_error"}, {"status": "discovered", "control": "failed"}])
def test_patch_needs_exact_discovery_and_passing_control_but_blocked_is_admitted(observed):
    agent = lambda final, retries: create_test_authoring_agent(responding([write(), RUN], final), output_retries=retries)
    with pytest.raises(UnexpectedModelBehavior):
        run(agent(PATCH, 0), case().inputs.inputs, runner(observed))
    blocked = {"status": "blocked", "layer": "discovery", "reason": "Collection failed on every run"}
    (result, _) = run(agent(blocked, 0), case().inputs.inputs, runner(observed))
    assert isinstance(result.output, BlockedAuthoring) and result.output.files[0].content == REFERENCE
    assert len(result.output.dev_runs) == 1


def test_run_budget_is_operator_owned_and_a_spent_budget_leaves_only_the_output():
    offered = []
    blocked = {"status": "blocked", "layer": "discovery", "reason": "Budget spent"}
    (result, fake) = run(create_test_authoring_agent(responding([write(), RUN, RUN], blocked, offered=offered)),
                         case().inputs.inputs, runner({"status": "collection_error"}, {"status": "collection_error"}),
                         budget=AuthoringBudget(dev_runs=2))
    assert len(fake.calls) == 2 and [r.status for r in result.output.dev_runs] == ["collection_error"] * 2
    assert offered == [ALL_TOOLS] * 3 + [READ_ONLY]
    with pytest.raises(ValueError):
        AuthoringBudget(dev_runs=0)


def test_tools_stay_offered_while_a_run_can_still_verify_a_fix():
    """A collection error with budget left is a test-code problem the author may fix; the patch is still admitted
    from the final in-budget run after writes and runs disappear."""
    offered = []
    (result, fake) = run(create_test_authoring_agent(responding([write(FILES["broken"]), RUN, write(), RUN],
                                                                offered=offered)),
                         case().inputs.inputs, runner({"status": "collection_error"}, {"status": "discovered"}),
                         budget=AuthoringBudget(dev_runs=2))
    assert isinstance(result.output, TestPatch) and len(fake.calls) == 2
    assert offered == [ALL_TOOLS] * 4 + [READ_ONLY]


class RefusingWorkspace:
    """The PLAN-0031 shape: the workspace refuses every patch before any interpreter runs."""

    def __init__(self):
        self.calls = []

    def run(self, patch, *, control_test_id, security_test_id, discovery_command, operation):
        self.calls.append(patch.sha256)
        return NativeTestRun(str(operation), patch.sha256, None, None, None, "not_required", "workspace",
                             "reviewed workspace refused the patch")


def test_workspace_failure_hides_writes_and_runs_so_the_author_returns_blocked():
    offered, refusing = [], RefusingWorkspace()
    blocked = {"status": "blocked", "layer": "sandbox", "reason": "The workspace refused the patch before tests ran"}
    (result, _) = run(create_test_authoring_agent(responding([write(), RUN], blocked, offered=offered)),
                      case().inputs.inputs, refusing)
    assert offered == [ALL_TOOLS, ALL_TOOLS, READ_ONLY] and len(refusing.calls) == 1
    assert isinstance(result.output, BlockedAuthoring) and result.output.layer == "sandbox"
    assert [r.status for r in result.output.dev_runs] == ["workspace_failure"]
    # A model that tries to rewrite and rerun anyway reaches no write or run.
    refusing = RefusingWorkspace()
    with pytest.raises(UnexpectedModelBehavior):
        run(create_test_authoring_agent(responding([write(), RUN, write(FILES["broken"]), RUN], blocked)),
            case().inputs.inputs, refusing)
    assert len(refusing.calls) == 1


def test_runs_requested_together_reserve_budget_and_only_the_first_runs():
    seen = []
    two = (ToolCallPart("run_tests", {}, tool_call_id="first"), ToolCallPart("run_tests", {}, tool_call_id="second"))
    blocked = {"status": "blocked", "layer": "unknown", "reason": "Stopped"}
    (result, fake) = run(create_test_authoring_agent(responding([write(), two], blocked, seen)), case().inputs.inputs,
                         runner({"status": "discovered"}, {"status": "discovered"}), budget=AuthoringBudget(dev_runs=1))
    assert len(fake.calls) == 1
    runs = sorted(result.output.dev_runs, key=lambda r: r.run)
    assert [(r.run, r.status) for r in runs] == [(1, "discovered"), (2, "not_run")]
    # With budget left, a second call in the same response would blindly repeat the first run's patch.
    (result, fake) = run(create_test_authoring_agent(responding([write(), two], blocked)), case().inputs.inputs,
                         runner({"status": "discovered"}, {"status": "discovered"}))
    assert len(fake.calls) == 1
    assert sorted((r.run, r.status) for r in result.output.dev_runs) == [(1, "discovered"), (2, "not_run")]
    refusing = RefusingWorkspace()
    (result, _) = run(create_test_authoring_agent(responding([write(), two], blocked)), case().inputs.inputs, refusing)
    assert len(refusing.calls) == 1
    assert sorted((r.run, r.status) for r in result.output.dev_runs) == [(1, "workspace_failure"), (2, "not_run")]
    (result, fake) = run(create_test_authoring_agent(responding([write(), two])), case().inputs.inputs,
                         runner({"status": "discovered"}), budget=AuthoringBudget(dev_runs=1))
    assert isinstance(result.output, TestPatch) and len(fake.calls) == 1
    assert sorted(r.status for r in result.output.dev_runs) == ["discovered", "not_run"]


def test_skipped_security_is_shown_and_refuses_a_patch_by_default():
    seen = []
    skipped = {"status": "discovered", "security": "skipped"}
    with pytest.raises(UnexpectedModelBehavior):
        run(create_test_authoring_agent(responding([write(), RUN], seen=seen), output_retries=0), case().inputs.inputs,
            runner(skipped))
    assert seen[0].security.outcome == "skipped"
    blocked = {"status": "blocked", "layer": "fixture", "reason": "The security test was skipped"}
    (result, _) = run(create_test_authoring_agent(responding([write(), RUN], blocked)), case().inputs.inputs, runner(skipped))
    assert isinstance(result.output, BlockedAuthoring)


def test_security_outcome_is_withheld_unless_the_operator_reveals_it():
    seen = []
    run(create_test_authoring_agent(responding([write(), RUN], seen=seen)), case().inputs.inputs)
    assert seen[0].security == "withheld" and seen[0].control.outcome == "passed"
    run(create_test_authoring_agent(responding([write(), RUN], seen=seen)), case().inputs.inputs,
        budget=AuthoringBudget(reveal_security_outcome=True))
    assert seen[0].security.outcome == "failed" and seen[0].security.failure_type == "AssertionError"


def test_previous_run_writes_and_runs_do_not_authorize_a_patch():
    c = case()
    (prior, _) = run(create_test_authoring_agent(responding([write(), RUN])), c.inputs.inputs)
    with pytest.raises(UnexpectedModelBehavior):
        run(create_test_authoring_agent(responding([]), output_retries=0), c.inputs.inputs,
            message_history=prior.all_messages())


def test_input_refuses_unapproved_or_mismatched_plans():
    data = case().inputs.inputs.model_dump()
    for change in (lambda d: d["plan"]["security"].update(test_path="tests/elsewhere.py"),
                   lambda d: d["environment"].update(discovery_command=["pytest"]),
                   lambda d: d["environment"].update(approved_test_paths=["test_documents.py", "documents.py"]),
                   lambda d: d["plan"]["security"].update(test_id="test_other.py::test_x"),
                   lambda d: d["plan"]["security"].update(test_id="test_documents.py::test_" + "x" * 120),
                   lambda d: d["plan"]["citations"][0].update(quote=d["plan"]["citations"][0]["quote"] + " "),
                   lambda d: d["source_files"][0].update(content="# another revision\n" + d["source_files"][0]["content"])):
        altered = TestAuthoringInput.model_validate(data).model_dump()
        change(altered)
        with pytest.raises(ValidationError):
            TestAuthoringInput.model_validate(altered)


@pytest.mark.parametrize("edit,check", [
    (lambda s: s.replace("import pytest", "import pytest\nfrom unittest import mock"), "no_mock"),
    (lambda s: s.replace("def test_security", "@pytest.mark.skip\ndef test_security"), "no_skip"),
    (lambda s: s.replace("except ValueError as error:", "except Exception as error:"), "no_swallowing_except"),
    (lambda s: s.replace("assert result is None", "assert True"), "no_constant_assert"),
    (lambda s: s.replace("documents.read_document(allowed, \"../outside.txt\")", "None"), "calls_target"),
])
def test_static_checks_flag_hollow_tests(edit, check):
    assert all(static_checks(REFERENCE, SECURITY, "read_document").values())
    assert not static_checks(edit(REFERENCE), SECURITY, "read_document")[check]


def test_assertion_lines_belong_to_the_named_function():
    assert assertion_lines(REFERENCE, SECURITY) == (52, 60, 64, 65, 66)
    with pytest.raises(ValueError):
        assertion_lines("def test_x(:\n", "t.py::test_x")
    with pytest.raises(ValueError):
        assertion_lines("def test_x():\n    pass\n", "t.py::test_x")


@pytest.mark.parametrize("body", [
    "def test_x():\n    def unused():\n        assert False\n",
    "def test_x():\n    check = lambda: [x for x in ()]\n    class Helper:\n        def m(self):\n            assert False\n",
    "def test_x(obj):\n    with obj.raises(ValueError):\n        pass\n",
    "def raises(e):\n    return open(__file__)\n\ndef test_x():\n    with raises(ValueError):\n        pass\n",
])
def test_unexecuted_or_non_pytest_checks_are_not_assertions(body):
    with pytest.raises(ValueError):
        assertion_lines(body, "t.py::test_x")
    assert not static_checks(body, "t.py::test_x", "x")["has_assertion"]


def test_pytest_raises_bindings_are_assertions():
    assert assertion_lines("import pytest as p\n\ndef test_x():\n    with p.raises(ValueError):\n        int('a')\n",
                           "t.py::test_x") == (4,)
    assert assertion_lines("from pytest import raises\n\ndef test_x():\n    with raises(ValueError):\n        int('a')\n",
                           "t.py::test_x") == (4,)


def test_native_evals_repeat_and_preserve_receipts(tmp_path):
    evidence = tmp_path / "attempt"
    report = asyncio.run(evaluate(evidence, EvaluationBudget()))
    assert passed(report) and len(report.cases) == 18 and len(report.case_groups()) == 9
    assert len(list(evidence.glob("attempt-*.json"))) == 18
    assert all(c.attributes["security_revealed"] == 0 for c in report.cases)
    assert report.experiment_metadata["runner"] == "injected_observations_and_static_host_runner"
    with pytest.raises(FileExistsError):
        asyncio.run(evaluate(evidence, EvaluationBudget()))


@pytest.mark.parametrize("reveal", [False, True])
def test_composes_with_the_native_runner_over_reviewed_bytes(tmp_path, reveal):
    """Scripted author writes only the reviewed SPEC-0018 bytes, so the reviewed host execution double may run them."""
    data = case().inputs.inputs.model_dump()
    data["plan"]["discovery_command"] = data["environment"]["discovery_command"] = list(DISCOVER)
    inputs = TestAuthoringInput.model_validate(data)
    root = (tmp_path / "workspace").resolve()
    (tmp_path / "artifacts").mkdir(mode=0o700)
    with LocalArtifacts(tmp_path / "artifacts", max_bytes=1024 * 1024) as store:
        _compose(inputs, root, store, reveal)


def _compose(inputs, root, store, reveal):
    native = PytestRunner(ReviewedWorkspace(store, root, "vulnerable"), ReviewedLocalExecution(root), store,
                          PytestRunnerConfig(PREFIX, ".corsair-junit.xml", str(root)))
    seen = []
    (result, _) = run(create_test_authoring_agent(responding([*READS, write(), RUN], seen=seen)), inputs, native,
                      budget=AuthoringBudget(reveal_security_outcome=reveal))
    patch = result.output
    assert isinstance(patch, TestPatch) and patch.dev_runs[0].status == "discovered"
    assert patch.dev_runs[0].control.outcome == "passed" and patch.run_command[:2] == ("/bin/sh", "-c")
    if reveal:
        failure = seen[0].security
        assert (failure.outcome, failure.failure_type, failure.failure_path) == ("failed", "AssertionError", "test_documents.py")
        assert failure.failure_line in patch.security_assertion_lines
    else:
        assert patch.dev_runs[0].security == "withheld"


HOOKED = "import sys\nimport documents\n\nsys.addaudithook(lambda e, a: None)\n\n\ndef test_benign_control(tmp_path):\n    assert True\n"


@pytest.mark.parametrize("content, facility", [
    (HOOKED, "sys.addaudithook"),
    ("import sys as s\ns.monitoring.use_tool_id(3, 'x')\n", "sys.monitoring"),
    ("from sys import addaudithook as hook\nhook(print)\n", "import sys.addaudithook"),
    ("import sys\nsys.audit('open', 'x')\n", "sys.audit"),
    ("import sys\ngetattr(sys, 'addaudithook')(print)\n", "string 'addaudithook'"),
    ("import threading\nthreading.settrace(print)\n", "threading.settrace"),
    ("def test_x(monkeypatch):\n    monkeypatch.setattr('builtins.open', print)\n",
     "monkeypatch.setattr(builtins.open)"),
    ("import os\n\ndef test_x(monkeypatch):\n    monkeypatch.setattr(os, 'open', print)\n", "monkeypatch.setattr(os)"),
    ("import documents\n\ndef test_x(monkeypatch):\n    monkeypatch.setattr(documents, 'open', print)\n",
     "monkeypatch.setattr(documents)"),
    ("from unittest import mock\n", "import unittest.mock"),
    ("import ctypes\n", "import ctypes"),
    ("import sys\n\ndef test_x(monkeypatch):\n    monkeypatch.setitem(sys.modules, 'documents', None)\n",
     "monkeypatch.setitem(sys.modules)"),
])
def test_self_observation_is_found_by_line(content, facility):
    findings = self_observation(content)
    assert facility in {f.facility for f in findings} and all(f.line >= 1 for f in findings)


def test_plain_tests_and_reviewed_bytes_are_admitted():
    plain = ("import os\nimport sys\nfrom pathlib import Path\n\nimport documents\n\n\ndef test_x(tmp_path: Path, monkeypatch):\n"
             "    monkeypatch.setenv('HOME', str(tmp_path))\n    monkeypatch.setitem(os.environ, 'LANG', 'C')\n"
             "    monkeypatch.setattr(sys, 'argv', ['tool'])\n    (tmp_path / 'a').write_text('s')\n"
             "    with open(tmp_path / 'a') as f:\n        assert f.read() == 's'\n    assert os.path.exists(tmp_path)\n")
    assert self_observation(plain) == () and self_observation("def broken(:\n") == ()
    assert self_observation("LABEL = 'monitoring dashboard'\n") == ()
    # The SPEC-0018 pair predates the witness and observes opens itself; it is admitted by its reviewed digest only.
    assert sha256(REFERENCE.encode()).hexdigest() in REVIEWED_SELF_OBSERVING and self_observation(REFERENCE) == ()
    assert self_observation(REFERENCE + "\n")


def test_refused_write_keeps_previous_content_and_the_author_can_act_once():
    offered = []
    agent = create_test_authoring_agent(responding([write(HOOKED), write(), RUN], offered=offered))
    result, fake = run(agent, case().inputs.inputs)
    assert isinstance(result.output, TestPatch) and len(fake.calls) == 1
    assert [f.content for f in result.output.files] == [REFERENCE]
    refusal = next(p.content for m in result.all_messages() for p in m.parts
                   if isinstance(p, ToolReturnPart) and p.tool_name == "write_test_file")
    assert refusal.status == "refused" and refusal.refusals_left == 1 and "line 4: sys.addaudithook" in refusal.reason
    assert offered[1:4] == [ALL_TOOLS] * 3


def test_the_author_reads_its_own_latest_admitted_write_and_absent_paths_are_typed_not_fatal():
    read = lambda path, start=1: ToolCallPart("read_source", {"path": path, "start_line": start})
    steps = [read("test_documents.py"), write(), write(HOOKED), read("test_documents.py"), read("test_documents.py", 999),
             read("conftest.py"), read("../outside.txt"), RUN]
    result, fake = run(create_test_authoring_agent(responding(steps)), case().inputs.inputs)
    assert isinstance(result.output, TestPatch) and len(fake.calls) == 1
    reads = [p.content for m in result.all_messages() for p in m.parts
             if isinstance(p, ToolReturnPart) and p.tool_name == "read_source"]
    unwritten, own, past, absent, outside = reads
    assert unwritten.status == "not_in_source" and "not written yet" in unwritten.reason
    # The refused write left the reference in place, and that is what the author reads back.
    assert "\n".join(line.text for line in own.lines) == "\n".join(REFERENCE.splitlines()[:80]) and own.start_line == 1
    assert past.status == "past_end" and f"has {len(REFERENCE.splitlines())} lines" in past.reason
    assert absent.status == outside.status == "not_in_source" and "test_documents.py" in absent.reason
    assert "write it again in full" in absent.reason


def test_second_refusal_ends_blocked_at_admission():
    offered = []
    draft = {"status": "blocked", "layer": "unknown", "reason": "refused"}
    agent = create_test_authoring_agent(responding([write(HOOKED), write(HOOKED)], final=draft, offered=offered))
    result, fake = run(agent, case().inputs.inputs)
    assert isinstance(result.output, BlockedAuthoring) and result.output.layer == "admission"
    assert "sys.addaudithook" in result.output.reason and result.output.files == () and fake.calls == []
    assert offered[-1] == READ_ONLY
    # A patch draft after the refusals is overruled the same way.
    agent = create_test_authoring_agent(responding([write(HOOKED), write(), RUN, write(HOOKED)]))
    result, fake = run(agent, case().inputs.inputs)
    assert isinstance(result.output, BlockedAuthoring) and result.output.layer == "admission" and len(fake.calls) == 1


def test_tools_are_withdrawn_at_the_tool_call_cap_and_the_author_returns_its_output():
    offered = []
    steps = [ToolCallPart("read_source", {"path": "documents.py"}), write(), RUN, write(), RUN]

    async def respond(messages, info):
        offered.append([t.name for t in info.function_tools])
        done = sum(isinstance(p, ToolReturnPart) for m in messages for p in m.parts)
        if info.function_tools and done < len(steps):
            return ModelResponse(parts=[replace(steps[done], tool_call_id=f"call-{done}")])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"result": PATCH})])
    inputs = case().inputs.inputs
    result = create_test_authoring_agent(FunctionModel(respond)).run_sync(
        authoring_prompt(inputs), deps=AuthoringDependencies(inputs, runner()),
        usage_limits=UsageLimits(request_limit=8, tool_calls_limit=3))
    assert isinstance(result.output, TestPatch) and result.usage.tool_calls == 3
    assert offered == [ALL_TOOLS, ALL_TOOLS, ALL_TOOLS, []]


@pytest.mark.parametrize("content, facility", [
    ("import socket as net\n\ndef test_x(monkeypatch):\n    monkeypatch.setattr(net, 'create_connection', print)\n",
     "monkeypatch.setattr(socket)"),
    ("import io\nio.open = lambda *a, **k: None\n", "assign io.open"),
    ("import os as o\ndel o.system\n", "delete os.system"),
    ("from os import path as p\np.exists = bool\n", "assign os.path.exists"),
    ("import builtins as b\nb.__dict__['open'] = print\n", "import builtins"),
    ("import sys\nsys.modules['documents'] = None\n", "assign sys.modules"),
    ("import subprocess as sp\nsp.run += print\n", "assign subprocess.run"),
    # Re-review on #49: the application's own bindings of protected names, written directly.
    ("import documents\ndocuments.open = lambda *a, **k: None\n", "assign documents.open"),
    ("import documents as d\ndel d.open\n", "delete documents.open"),
    ("import documents\ndocuments.__dict__['open'] = print\n", "assign documents.__dict__"),
    ("import documents\ndocuments.subprocess.run = print\n", "assign documents.subprocess.run"),
    ("import documents\n\ndef test_x(monkeypatch):\n    monkeypatch.setattr(documents.os, 'open', print)\n",
     "monkeypatch.setattr(documents.os)"),
    # Claude review on 236bdab: string targets, references through the target module, keyword arguments.
    ("def test_x(monkeypatch):\n    monkeypatch.setattr('app.mod.subprocess.run', print)\n",
     "monkeypatch.setattr(app.mod.subprocess.run)"),
    ("def test_x(monkeypatch):\n    monkeypatch.setattr('app.mod.open', print)\n", "monkeypatch.setattr(app.mod.open)"),
    ("import app.mod as m\nm.subprocess.run = print\n", "assign app.mod.subprocess.run"),
    ("from app.mod import os as aos\naos.system = print\n", "assign app.mod.os.system"),
    ("def test_x(monkeypatch):\n    monkeypatch.setattr(target='os.system', value=print)\n",
     "monkeypatch.setattr(os.system)"),
    ("import os\n\ndef test_x(monkeypatch):\n    monkeypatch.setattr(target=os, name='system', value=print)\n",
     "monkeypatch.setattr(os)"),
    # Forged events and monitoring by computed name, star import or dynamic import.
    ("import sys\ngetattr(sys, 'audit')('open', '/x', 'r')\n", "getattr()"),
    ("import sys\ngetattr(sys, 'monitoring').use_tool_id(3, 'x')\n", "getattr()"),
    ("import sys\nsys.__dict__['audit']('open', '/x', 'r')\n", "sys.__dict__"),
    ("import operator\nimport sys\noperator.attrgetter('audit')(sys)\n", "operator.attrgetter()"),
    ("from sys import *\naddaudithook(print)\n", "import sys.*"),
    ("import importlib\nimportlib.import_module('ctypes')\n", "importlib.import_module()"),
    ("import importlib\nimportlib.__import__('ctypes')\n", "importlib.__import__"),
    ("import os\nvars(os)['system'] = print\n", "vars()"),
    # Re-review on 538fb4b: member-import aliases of the dynamic functions.
    ("from operator import attrgetter as get\nimport sys\nget('audit')(sys)('open', '/x', 'r')\n", "get()"),
    ("from operator import methodcaller as call\nimport sys\ncall('audit', 'open')(sys)\n", "call()"),
    ("import operator as op\nimport sys\nop.attrgetter('audit')(sys)\n", "op.attrgetter()"),
    # Follow-up review on ecda72d: in-place mutation of a protected mapping.
    ("import sys\nimport types\nsys.modules.update({'app.dep': types.ModuleType('app.dep')})\n", "sys.modules.update()"),
    ("import sys\nsys.modules.setdefault('app.dep', None)\n", "sys.modules.setdefault()"),
    ("import sys\nsys.modules.pop('app.dep')\n", "sys.modules.pop()"),
    # Codex review on 78f1690: a computed member name, and a module reached through a local rebinding.
    ("import documents\n\ndef test_x(monkeypatch):\n    name = 'open'\n    monkeypatch.setattr(documents, name, print)\n",
     "monkeypatch.setattr(computed name)"),
    ("import documents\n\ndef test_x(monkeypatch):\n    d = documents\n    monkeypatch.setattr(d, 'open', print)\n",
     "monkeypatch.setattr(documents)"),
    ("import documents as x\nd = x\ne = d\ne.subprocess = None\n", "assign documents.subprocess"),
    ("import documents\n\ndef test_x(monkeypatch):\n    if (d := documents):\n        monkeypatch.setattr(d, 'open', print)\n",
     "monkeypatch.setattr(documents)"),
])
def test_aliased_and_direct_patches_of_observed_facilities_are_found(content, facility):
    """Review on #49: aliases of protected modules and plain assignments must not bypass admission."""
    assert facility in {f.facility for f in self_observation(content)}


def test_rebinding_a_local_name_or_setting_the_environment_is_not_a_patch():
    assert self_observation("import os\nos.environ['LANG'] = 'C'\nopen_count = 0\n") == ()
    assert self_observation("import documents\ndocuments.CONFIG = {}\ndocuments.os_name = 'x'\n") == ()
    assert self_observation("import re\nimport app.mod as m\nPATTERN = re.compile('x')\nm.os.environ['LANG'] = 'C'\n") == ()
    # Writes on local objects are not facility patches, whatever the attribute or key is called.
    assert self_observation("c = object()\nc.open = 1\npayload = {}\npayload['os'] = 'linux'\npayload['open'] = True\n"
                            "def test_x(monkeypatch, fake):\n    monkeypatch.setattr(fake, 'open', 1)\n") == ()
    assert self_observation("import os\nimport app.mod as m\nos.environ.update({'A': '1'})\nm.os.environ.update({})\n") == ()
    # Objects built by a call stay local; environment keys may be computed.
    assert self_observation("import documents\nc = documents.Client()\nc.open = 1\n\ndef test_x(monkeypatch):\n"
                            "    k = 'HOME'\n    monkeypatch.setitem(documents.os.environ, k, '/tmp')\n"
                            "    monkeypatch.setattr('documents.LIMIT', k)\n") == ()


@pytest.mark.parametrize("deferred", [
    "    def never_called():\n        read_document()\n",
    "    class Helper:\n        def never_called(self):\n            read_document()\n",
    "    call = lambda: read_document()\n",
])
def test_deferred_target_calls_do_not_satisfy_structural_target_fact(deferred):
    content = "def test_security():\n" + deferred + "    actual = 1\n    assert actual == 1\n"
    facts = static_checks(content, "t.py::test_security", "read_document")
    assert facts["has_assertion"] and not facts["calls_target"]
    direct = content + "    read_document()\n"
    assert static_checks(direct, "t.py::test_security", "read_document")["calls_target"]
