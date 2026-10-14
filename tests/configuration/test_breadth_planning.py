"""The frozen planning breadth set: per-language coverage and evaluator sensitivity to plausible wrong plans."""

from collections import Counter

import pytest

from corsair.agents.test_planning.contracts import ReadyTestPlan, UnsupportedTestPlan
from evals.cases import load_set
from evals.test_planning.evaluate import dataset, plan_checks

CASES = {case.name: case for case in dataset("breadth").cases}


def _quoted(inputs, plan: dict) -> dict:
    """Attach trusted quotations the way finalization does, so a reference plan becomes a final output."""
    contents = {source.path: source.content.splitlines() for source in inputs.source_files}

    def quote(reference):
        lines = contents[reference["path"]][reference["start_line"] - 1:reference["end_line"]]
        return {**reference, "quote": "\n".join(lines)}

    data = {**plan, "citations": [quote(reference) for reference in plan["citations"]]}
    for name in ("control", "security"):
        if name in data:
            data[name] = {**data[name], "source_references": [quote(r) for r in data[name]["source_references"]]}
    return data


def _output(case, plan=None):
    data = _quoted(case.inputs, plan or case.metadata.reference_plan)
    model = ReadyTestPlan if data["status"] == "ready" else UnsupportedTestPlan
    return model.model_validate(data, context=case.inputs)


def _failed(case, output) -> set[str]:
    return {name for name, ok in plan_checks(case.inputs, output, case.metadata).items() if not ok}


def test_breadth_language_counts():
    counts = Counter(case.case["language"] for case in load_set("test_planning", "breadth"))
    assert counts == {"java": 10, "javascript": 10, "ruby": 10, "perl": 10}
    kinds = {(case.case["language"], case.case["kind"]) for case in load_set("test_planning", "breadth")}
    for language in ("java", "javascript", "ruby", "perl"):
        assert {(language, kind) for kind in ("positive", "guarded", "injection", "abstention", "transfer")} <= kinds


@pytest.mark.parametrize("name", sorted(CASES))
def test_reference_plan_passes(name):
    case = CASES[name]
    assert _failed(case, _output(case)) == set()


def test_blanket_approval_and_refusal_fail():
    ready = [case for case in CASES.values() if case.metadata.status == "ready"]
    unsupported = [case for case in CASES.values() if case.metadata.status == "unsupported"]
    assert len(unsupported) == 12 and len(ready) == 28
    for case in ready:
        refusal = UnsupportedTestPlan.model_validate(_quoted(case.inputs, {
            "status": "unsupported", "scope": "component", "missing_capability": "No suitable observation",
            "limitations": ["none"], "citations": case.metadata.reference_plan["citations"]}), context=case.inputs)
        assert "status" in _failed(case, refusal), case.name
    for case in unsupported:
        # A plausible blanket approval: a ready plan for the same language reused against this case.
        language = case.name.split("-", 1)[0]
        donor = next(c for c in ready if c.name.startswith(language + "-"))
        assert "status" in _failed(case, _output(donor)), case.name


def test_wrong_symbol_kind_and_injected_text_fail():
    for case in (c for c in CASES.values() if c.metadata.status == "ready"):
        plan = case.metadata.reference_plan
        other_kind = "return_value" if case.metadata.observation_kind != "return_value" else "exception"
        wrong = {**plan, **{name: {**plan[name], "implementation_call": "helper(value)",
                                   "observation": {**plan[name]["observation"], "kind": other_kind,
                                                   "controlled_dependency": plan[name]["observation"].get("controlled_dependency")}}
                            for name in ("control", "security")}}
        assert {"implementation_call", "native_observation"} <= _failed(case, _output(case, wrong)), case.name
        swapped = {**plan, "control": {**plan["control"], "input": plan["security"]["input"]}}
        assert "adversarial_input" in _failed(case, _output(case, swapped)), case.name
        if case.metadata.forbidden_markers:
            obeyed = {**plan, "limitations": [*plan["limitations"], f"Injected: {case.metadata.forbidden_markers[0]}"]}
            assert "authority" in _failed(case, _output(case, obeyed)), case.name
