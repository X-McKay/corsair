"""Authoring breadth sets: per-language counts, scripted pass, evaluator sensitivity and the pending set's one reason."""

import asyncio
from collections import Counter

import pytest

from corsair.agents.test_authoring.contracts import TestPatch
from corsair.agents.test_planning.contracts import ReadyTestPlan
from evals.cases import load_set
from evals.test_authoring import languages
from evals.test_authoring.evaluate import (
    AuthoringOracle,
    EvaluationBudget,
    authoring_checks,
    dataset,
    evaluate,
    passed,
    pending,
)

SUITE = "test_authoring"


def test_breadth_counts_by_language():
    corpus = dataset("breadth")
    cases = load_set(SUITE, "breadth")
    assert [case.name for case in corpus.cases] == [case.name for case in cases]
    assert Counter(case.case["language"] for case in cases) == {"ruby": 10}
    pending_cases = load_set(SUITE, "breadth_pending")
    assert Counter(case.case["language"] for case in pending_cases) == {"javascript": 10, "java": 10, "perl": 10}
    assert {case.case["kind"] for case in pending_cases} == {"pending-reader"}
    assert all(case.case["pending"]["missing"] for case in pending_cases)


@pytest.fixture(scope="module")
def breadth_report(tmp_path_factory):
    return asyncio.run(evaluate(tmp_path_factory.mktemp("authoring") / "breadth", EvaluationBudget(repeat=1),
                                cases="breadth"))


def test_breadth_passes_scripted(breadth_report):
    assert passed(breadth_report)


def _case(report, name):
    return next(case for case in report.cases if case.name == name)


def _rewrite(output: TestPatch, old: str, new: str) -> TestPatch:
    files = tuple(item.model_copy(update={"content": item.content.replace(old, new)}) for item in output.files)
    assert files != output.files
    return output.model_copy(update={"files": files})


def test_wrong_outputs_fail(breadth_report):
    reference = _case(breadth_report, "ruby-reference-realization")
    inputs, oracle, output = reference.inputs.inputs, reference.metadata, reference.output
    assert all(authoring_checks(inputs, output, oracle).values())
    # A blanket patch where the stage must end blocked.
    for name in ("ruby-persistent-collection-error", "ruby-failing-control"):
        blocked = _case(breadth_report, name)
        assert not authoring_checks(blocked.inputs.inputs, output, blocked.metadata)["status"]
    wrong = {
        "planned_input_in_security": _rewrite(output, "'../secret.txt'", "'todo.txt'"),
        "planned_input_not_in_control": _rewrite(output, "Notes.read(root, 'todo.txt')", "Notes.read(root, '../secret.txt')"),
        "static_semantics": _rewrite(output, "assert_nil Notes.read(root, '../secret.txt')",
                                     "Notes.list(root, '../secret.txt')\n      assert true"),
        "no_process_or_network": _rewrite(output, "require 'tmpdir'", "require 'tmpdir'\nsystem('id')"),
    }
    for fact, patch in wrong.items():
        assert authoring_checks(inputs, patch, oracle)[fact] is False, fact
    skipped = _rewrite(output, "  def test_security_stays_inside_root\n", "  def test_security_stays_inside_root\n    skip\n")
    assert not authoring_checks(inputs, skipped, oracle)["static_semantics"]


def _plan_and_file(case):
    return (ReadyTestPlan.model_validate(case.input["inputs"]["plan"]),
            AuthoringOracle.model_validate(case.oracle).files["reference"])


def test_pending_realisations_read_today_where_a_reader_exists():
    """Jest realisations satisfy every eval fact through the production reader; JUnit and TAP ones satisfy the
    lexical facts, and the reader-backed ones stay false until a reader lands."""
    for case in load_set(SUITE, "breadth_pending"):
        plan, content = _plan_and_file(case)
        language = case.case["language"]
        files = {plan.security.test_path: content}
        lines = tuple(case.oracle.get("security_assertion_lines", ()))
        for spec in (plan.control, plan.security):
            facts = languages.static_facts(language, content, spec.test_id, spec.implementation_call)
            if language == "javascript":
                assert all(facts.values()), (case.name, facts)
            else:
                assert facts == {"parses_and_defines_test": False}, case.name
                assert languages._calls(languages.body_of(language, content, spec.test_id),
                                        languages._callee(spec.implementation_call)), case.name
        admission = languages.admission_facts(language, plan, files, lines)
        expected = {key: True for key in admission}
        if "planned_failure_is_assert" in admission and (language != "javascript" or not lines):
            # No reader for JUnit or TAP yet; blocked cases name no assertion lines.
            expected["planned_failure_is_assert"] = False
        assert admission == expected, (case.name, admission)


def test_pending_fails_only_for_the_missing_language_support(tmp_path):
    """Today every pending case is refused as input by the authoring id grammar and for nothing else; when that
    support lands this assertion fails on purpose, and the cases move to breadth once they pass."""
    outcomes = asyncio.run(pending(tmp_path / "pending", EvaluationBudget(repeat=1)))
    for case in load_set(SUITE, "breadth_pending"):
        control = case.input["inputs"]["plan"]["control"]["test_id"]
        assert outcomes[case.name] == {
            "outcome": "refused_input",
            "reason": f"Value error, planned test id {control} is not a supported native node id"}, case.name
