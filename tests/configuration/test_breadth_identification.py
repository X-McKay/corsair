"""Breadth set for issue identification: per-language counts and evaluator sensitivity (no model, no provider)."""

from collections import Counter

from corsair.agents.issue_identification.contracts import IssueIdentification
from evals.cases import load_set
from evals.issue_identification.evaluate import dataset, selection_checks

CLAIMED = {"python": 4, "java": 10, "javascript": 10, "ruby": 10, "perl": 10}


def _output(inputs, status, path=None, start=1, end=1, symbol=None):
    if status != "ready":
        return IssueIdentification(status=status, scope=inputs.scope, target=None, reason="not established",
                                   reported_issue=inputs.issue)
    lines = next(item for item in inputs.source_files if item.path == path).content.splitlines()
    quote = "\n".join(lines[start - 1:end])
    return IssueIdentification(status="ready", scope=inputs.scope, reason=None, reported_issue=inputs.issue,
                               target={"symbol": symbol, "source": {"path": path, "start_line": start,
                                                                    "end_line": end, "quote": quote}})


def _passes(case, output):
    return all(selection_checks(case.inputs, output, case.metadata).values())


def test_breadth_loads_through_suite_dataset_with_claimed_language_counts():
    corpus = dataset("breadth")
    meta = {case.name: case.case for case in load_set("issue_identification", "breadth")}
    assert [case.name for case in corpus.cases] == list(meta)
    assert Counter(m["language"] for m in meta.values()) == CLAIMED
    for language in CLAIMED:
        statuses = {case.metadata.status for case in corpus.cases if meta[case.name]["language"] == language}
        assert statuses == {"ready", "missing_information"}, language


def test_oracle_selection_passes_every_check():
    for case in dataset("breadth").cases:
        oracle = case.metadata
        if oracle.status == "ready":
            output = _output(case.inputs, "ready", oracle.path, min(oracle.required_lines), max(oracle.required_lines),
                             oracle.symbol)
        else:
            output = _output(case.inputs, oracle.status)
        assert _passes(case, output), case.name


def test_plausible_wrong_outputs_fail():
    corpus = dataset("breadth").cases
    for case in corpus:
        oracle = case.metadata
        first = next(item for item in case.inputs.source_files if item.content.strip())
        line = next(n for n, text in enumerate(first.content.splitlines(), 1) if text.strip())
        # Blanket "ready" on the first non-blank saved line fails every abstention and every other target.
        blanket = _output(case.inputs, "ready", first.path, line, line, "main")
        assert not _passes(case, blanket), case.name
        if oracle.status == "ready":
            assert not _passes(case, _output(case.inputs, "missing_information")), case.name
    decoys = 0
    for case in corpus:
        oracle = case.metadata
        if oracle.status != "ready":
            continue
        for other in case.inputs.source_files:
            lines = other.content.splitlines()
            hits = [n for n, line in enumerate(lines, 1) if oracle.symbol in line]
            if other.path != oracle.path and hits:
                decoys += 1
                wrong = _output(case.inputs, "ready", other.path, hits[0], min(hits[0] + 2, len(lines)), oracle.symbol)
                assert not _passes(case, wrong), case.name
    assert decoys >= 4  # same-name decoy files in each non-Python language and a caller module
