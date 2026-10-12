"""Exercise the authoring stage's confinement, run budget, withheld outcome and provenance through native SDK calls."""

import asyncio
from dataclasses import replace

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
from corsair.agents.test_authoring.skills import SKILL_TEXT
from corsair.agents.test_authoring.static import assertion_lines, static_checks
from tests.unit.test_pytest_runner import DISCOVER, PREFIX, ReviewedLocalExecution, ReviewedWorkspace
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


def responding(steps, final=PATCH, seen=None):
    async def respond(messages, info):
        assert "Write exactly the two planned tests" in info.instructions and SKILL_TEXT.strip() in info.instructions
        assert [t.name for t in info.function_tools] == ["read_source", "write_test_file", "run_tests"]
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


def test_run_budget_is_operator_owned_and_spent_runs_execute_nothing():
    seen = []
    steps = [write(), RUN, RUN, RUN]
    blocked = {"status": "blocked", "layer": "discovery", "reason": "Budget spent"}
    (result, fake) = run(create_test_authoring_agent(responding(steps, blocked, seen)), case().inputs.inputs,
                         runner({"status": "collection_error"}, {"status": "collection_error"}),
                         budget=AuthoringBudget(dev_runs=2))
    assert len(fake.calls) == 2 and [r.status for r in result.output.dev_runs] == ["collection_error"] * 2 + ["not_run"]
    with pytest.raises(ValueError):
        AuthoringBudget(dev_runs=0)


def test_runs_requested_together_each_reserve_budget_and_identity():
    seen = []
    two = (ToolCallPart("run_tests", {}, tool_call_id="first"), ToolCallPart("run_tests", {}, tool_call_id="second"))
    blocked = {"status": "blocked", "layer": "unknown", "reason": "Stopped"}
    (result, fake) = run(create_test_authoring_agent(responding([write(), two], blocked, seen)), case().inputs.inputs,
                         runner({"status": "discovered"}, {"status": "discovered"}), budget=AuthoringBudget(dev_runs=1))
    assert len(fake.calls) == 1
    runs = sorted(result.output.dev_runs, key=lambda r: r.run)
    assert [(r.run, r.status) for r in runs] == [(1, "discovered"), (2, "not_run")]
    (result, fake) = run(create_test_authoring_agent(responding([write(), two], blocked)), case().inputs.inputs,
                         runner({"status": "discovered"}, {"status": "discovered"}))
    operations = {r.operation for r in result.output.dev_runs}
    assert len(fake.calls) == 2 and len(operations) == 2
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
    assert passed(report) and len(report.cases) == 12 and len(report.case_groups()) == 6
    assert len(list(evidence.glob("attempt-*.json"))) == 12
    assert all(c.attributes["security_revealed"] == 0 for c in report.cases)
    assert report.experiment_metadata["runner"] == "scripted_observations"
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
