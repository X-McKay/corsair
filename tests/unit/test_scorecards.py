"""Scorecard queries over synthetic run records, and the safety/adversarial frozen sets."""

import json
from pathlib import Path

import pytest

from corsair.contracts import Disposition
from corsair.evaluation import scorecards
from corsair.evaluation.scoring import load_dataset

ROOT = Path(__file__).resolve().parents[2]

LE, LNE, INC, UTR, ERR = (
    "LIKELY_EXPLOITABLE",
    "LIKELY_NOT_EXPLOITABLE",
    "INCONCLUSIVE",
    "UNABLE_TO_RUN",
    "ERROR",
)


def row(case_id: str, label: str | None, expected: str | None, **overrides) -> dict:
    record = {
        "run_id": "run01",
        "case_id": case_id,
        "input_digest": f"digest-{case_id}",
        "language": "python",
        "runtime": "pytest",
        "cwe": "CWE-78",
        "label": label,
        "expected_label": expected,
        "decisive": label in {LE, LNE},
        "last_gate": "verdict",
        "rejections": [],
        "llm_calls": 4,
        "tool_calls": 6,
        "seconds": 10.0,
        "unrelated_extra_key": {"ignored": True},
    }
    record.update(overrides)
    return record


ROWS = [
    row("c1", LE, LE),
    row(
        "c2",
        LNE,
        LNE,
        cwe="CWE-89",
        rejections=[{"gate": "review", "rule": "R2"}],
        llm_calls=6,
        tool_calls=8,
        seconds=20.0,
    ),
    row(
        "c3",
        LNE,
        LE,
        language="javascript",
        runtime="jest",
        rejections=[{"gate": "review", "rule": "R2"}, {"gate": "review", "rule": "R5"}],
        llm_calls=5,
        tool_calls=5,
        seconds=5.0,
    ),
    row(
        "c4",
        INC,
        LE,
        language="javascript",
        runtime="jest",
        cwe="CWE-79",
        last_gate="review",
        rejections=[{"gate": "build", "rule": "B1"}],
        llm_calls=None,
        tool_calls=None,
        seconds=None,
    ),
    row(
        "c5",
        UTR,
        LNE,
        language="java",
        runtime="maven",
        cwe="CWE-89",
        last_gate="build",
        llm_calls=1,
        tool_calls=1,
        seconds=1.0,
    ),
    row("c6", ERR, None, language="perl", runtime="prove", last_gate="plan"),
]


def write_run(directory: Path, name: str, rows: list[dict]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.jsonl"
    path.write_text("".join(json.dumps(record) + "\n" for record in rows))
    return path


@pytest.fixture
def runs(tmp_path: Path) -> Path:
    write_run(tmp_path / "runs", "run01", ROWS)
    return tmp_path / "runs"


def metric(metrics, name, label=None):
    return next(item for item in metrics if item.metric == name and item.label == label)


def test_scorecard_reports_per_label_precision_recall_and_safe_label_cost(runs: Path):
    metrics = scorecards.scorecard(runs)

    assert (
        metric(metrics, "precision", LE).numerator,
        metric(metrics, "precision", LE).denominator,
    ) == (1, 1)
    assert metric(metrics, "recall", LE).value == pytest.approx(1 / 3)
    assert metric(metrics, "precision", LNE).value == 0.5
    assert metric(metrics, "recall", LNE).value == 0.5
    assert metric(metrics, "precision", INC).value == 0
    # Nothing was expected to be INCONCLUSIVE: an empty denominator is unknown, not zero.
    assert metric(metrics, "recall", INC).denominator == 0
    assert metric(metrics, "recall", INC).value is None
    assert {item.label for item in metrics if item.metric == "precision"} == {
        LE,
        LNE,
        INC,
        UTR,
        ERR,
    }

    assert metric(metrics, "safe_precision", LNE).value == 0.5
    false_safe = metric(metrics, "false_safe_rate", LNE)
    assert (false_safe.numerator, false_safe.denominator) == (1, 3)
    assert metric(metrics, "decisive_rate").value == 0.5
    assert metric(metrics, "llm_calls_per_decisive").value == 5
    assert metric(metrics, "tool_calls_per_decisive").value == pytest.approx(19 / 3)
    assert metric(metrics, "seconds_per_decisive").value == pytest.approx(35 / 3)
    assert metric(metrics, "usage_unknown_rate").value == pytest.approx(1 / 6)


def test_scorecard_uses_labels_from_the_data_and_a_parameterized_safe_label(runs: Path):
    metrics = scorecards.scorecard(runs, safe_label=INC)
    assert metric(metrics, "safe_precision", INC).value == 0
    assert metric(metrics, "false_safe_rate", INC).denominator == 5


def test_strata_cut_by_language_runtime_cwe_and_last_gate(runs: Path):
    strata = {(item.dimension, item.stratum): item for item in scorecards.strata(runs)}

    assert {dimension for dimension, _ in strata} == {"language", "runtime", "cwe", "last_gate"}
    python = strata[("language", "python")]
    assert (python.runs, python.decisive, python.correct, python.false_safe) == (2, 2, 2, 0)
    assert python.llm_calls == 10
    javascript = strata[("language", "javascript")]
    assert (javascript.runs, javascript.decisive, javascript.correct, javascript.false_safe) == (
        2,
        1,
        0,
        1,
    )
    assert javascript.llm_calls == 5
    assert javascript.usage_unknown == 1
    assert strata[("cwe", "CWE-89")].runs == 2
    assert strata[("last_gate", "build")].runs == 1
    assert strata[("runtime", "jest")].false_safe == 1


def test_ledger_counts_rejections_by_gate_and_rule(runs: Path):
    ledger = {(item.gate, item.rule): item for item in scorecards.ledger(runs)}
    assert ledger[("review", "R2")].rejections == 2
    assert ledger[("review", "R2")].runs == 2
    assert ledger[("review", "R5")].rejections == 1
    assert ledger[("build", "B1")].rejections == 1
    assert len(ledger) == 3


def test_read_scorecard_bundles_typed_results(runs: Path):
    card = scorecards.read_scorecard(runs)
    assert card.safe_label == LNE
    assert card.metrics and card.strata and card.ledger
    assert card.model_dump()["metrics"][0]["metric"]


def test_compare_refuses_runs_with_different_input_digests(tmp_path: Path):
    baseline = [row("c1", LE, LE), row("c2", INC, LNE)]
    candidate = [
        row("c1", LE, LE, run_id="run02"),
        row("c2", LNE, LNE, run_id="run02", input_digest="changed"),
    ]
    write_run(tmp_path / "baseline", "run01", baseline)
    write_run(tmp_path / "candidate", "run02", candidate)

    with pytest.raises(ValueError, match="c2"):
        scorecards.compare(tmp_path / "baseline", tmp_path / "candidate")


def test_compare_refuses_runs_with_missing_cases(tmp_path: Path):
    write_run(tmp_path / "baseline", "run01", [row("c1", LE, LE), row("c2", INC, LNE)])
    write_run(tmp_path / "candidate", "run02", [row("c1", LE, LE, run_id="run02")])

    with pytest.raises(ValueError, match="c2"):
        scorecards.compare(tmp_path / "baseline", tmp_path / "candidate")


def test_compare_reports_label_and_cost_deltas_over_identical_inputs(tmp_path: Path):
    write_run(tmp_path / "baseline", "run01", [row("c1", LE, LE), row("c2", INC, LNE)])
    write_run(
        tmp_path / "candidate",
        "run02",
        [row("c1", LE, LE, run_id="run02", llm_calls=6), row("c2", LNE, LNE, run_id="run02")],
    )

    comparison = {
        item.case_id: item
        for item in scorecards.compare(tmp_path / "baseline", tmp_path / "candidate")
    }
    assert comparison["c1"].llm_calls_delta == 2
    assert (comparison["c2"].baseline_label, comparison["c2"].candidate_label) == (INC, LNE)
    assert comparison["c2"].candidate_decisive is True


def test_missing_run_records_are_refused(tmp_path: Path):
    with pytest.raises(ValueError, match="no \\*.jsonl"):
        scorecards.scorecard(tmp_path)


def test_scorecards_module_never_imports_agents_or_model_sdks():
    source = (ROOT / "src/corsair/evaluation/scorecards.py").read_text()
    for forbidden in ("google", "litellm", "corsair.agents", "corsair.adapters", "temporalio"):
        assert forbidden not in source


@pytest.mark.parametrize(
    ("name", "forbidden_verdict"),
    [("safety", LNE), ("adversarial", LE)],
)
def test_safety_and_adversarial_sets_load_frozen_with_conservative_oracles(
    name: str, forbidden_verdict: str
):
    dataset, requests, oracles = load_dataset(ROOT / f"evals/datasets/{name}.json")
    assert len(requests) == len(dataset.entries) >= 2
    for request in requests:
        oracle = oracles[request.case.case_id]
        # A false "not exploitable" is the costliest error: no oracle ever accepts REFUTED,
        # and the canonical forbidden verdict names the error each set is built to catch.
        assert Disposition.REFUTED in oracle.forbidden
        assert Disposition.REFUTED not in oracle.acceptable
        assert forbidden_verdict in oracle.forbidden_verdicts
        assert oracle.acceptable_verdicts is not None
        assert forbidden_verdict not in oracle.acceptable_verdicts
        assert INC in oracle.acceptable_verdicts
