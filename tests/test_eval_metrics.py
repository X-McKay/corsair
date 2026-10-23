"""Offline checks of the eval metrics: frozen splits, repeat aggregation, precision and recall, unknown telemetry.

The repeat path runs through ``main`` with the investigation replaced by a scripted record; nothing calls a model.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from corsair import cli
from corsair.application.cases import load_case, load_oracle

ROOT = Path(__file__).resolve().parents[1]
E2E = ROOT / "evals/e2e"
V2 = E2E / "python/v2"
DEV = ROOT / "evals/e2e/sets/python-v2-dev.json"
HELDOUT = ROOT / "evals/e2e/sets/python-v2-heldout.json"
HELD_OUT_FAMILIES = {"deserialization", "massassignment", "pathtraversal", "ssrf", "xxe"}


def _paired_families() -> list[str]:
    names = {p.name for p in V2.iterdir() if p.is_dir()}
    return sorted({n[:-2] for n in names if n.endswith("-a") and n[:-2] + "-b" in names})


def _keys(path: Path) -> list[str]:
    return list(json.loads(path.read_text())["cases"])


def test_the_split_is_the_frozen_rule_over_the_paired_cases():
    families = _paired_families()
    assert len(families) == 15
    # the rule recorded in the set note: every third family in sorted order is held out
    assert {f for i, f in enumerate(families) if i % 3 == 2} == HELD_OUT_FAMILIES
    dev, held = _keys(DEV), _keys(HELDOUT)
    assert set(dev).isdisjoint(held)
    assert sorted(dev + held) == sorted(f"python/v2/{f}-{v}" for f in families for v in "ab")
    assert json.loads(DEV.read_text())["held_out"] is False
    assert json.loads(HELDOUT.read_text())["held_out"] is True


@pytest.mark.parametrize("path", [DEV, HELDOUT])
def test_each_split_keeps_families_whole_and_has_both_labels(path):
    cases = _keys(path)
    families = {k.rsplit("/", 1)[1][:-2] for k in cases}
    for family in families:
        assert {f"python/v2/{family}-a", f"python/v2/{family}-b"} <= set(cases)
    labels = {load_oracle(E2E / k)["expected_label"] for k in cases}
    assert labels == {"LIKELY_EXPLOITABLE", "LIKELY_NOT_EXPLOITABLE"}


def test_loading_a_set_refuses_an_oracle_that_changed_after_freezing(tmp_path):
    case = tmp_path / "evals/e2e/python/v2/x-a"
    case.mkdir(parents=True)
    (case / "oracle.json").write_text('{"expected_label": "LIKELY_EXPLOITABLE"}')
    sets = tmp_path / "evals/e2e/sets"
    sets.mkdir(parents=True)
    frozen = sets / "s.json"
    frozen.write_text(json.dumps({"held_out": False, "cases": {"python/v2/x-a": "0" * 64}}))
    with pytest.raises(SystemExit, match="changed since the set was frozen"):
        cli._load_set(frozen)


def _row(case, label, expected, *, repeat=1, requests=None, input_tokens=None, tool_calls=None):
    correct = None if expected is None else label in {expected}
    return {
        "case": case,
        "case_id": case,
        "repeat": repeat,
        "label": label,
        "expected_label": expected,
        "correct": correct,
        "forbidden_hit": False,
        "requests": requests,
        "input_tokens": input_tokens,
        "output_tokens": None,
        "tool_calls": tool_calls,
        "bash_calls": None,
        "duration_s": 1.0,
    }


def test_summary_reports_accuracy_precision_recall_and_inconclusive_rate():
    E, N = "LIKELY_EXPLOITABLE", "LIKELY_NOT_EXPLOITABLE"
    rows = [
        _row("a", E, E),
        _row("a", N, E),
        _row("a", "INCONCLUSIVE", E),  # recall misses for E: N and INCONCLUSIVE
        _row("b", N, N),
        _row("b", E, N),  # b: an N run that is right, and an E run that is a false positive
        _row("c", "UNABLE_TO_RUN", None),  # unscored, no truth
    ]
    m = cli.summarise(rows)
    assert (m["runs"], m["scored_runs"], m["correct_runs"]) == (6, 5, 2)
    assert m["accuracy"] == 0.4
    assert m["per_label"][E] == {"tp": 1, "fp": 1, "fn": 2, "precision": 0.5, "recall": pytest.approx(1 / 3)}
    assert m["per_label"][N] == {"tp": 1, "fp": 1, "fn": 1, "precision": 0.5, "recall": 0.5}
    assert m["inconclusive_rate"] == pytest.approx(1 / 6)
    assert m["label_counts"] == {
        "INCONCLUSIVE": 1,
        "LIKELY_EXPLOITABLE": 2,
        "LIKELY_NOT_EXPLOITABLE": 2,
        "UNABLE_TO_RUN": 1,
    }


def test_missing_telemetry_is_unknown_not_zero():
    rows = [
        _row("a", "LIKELY_EXPLOITABLE", "LIKELY_EXPLOITABLE", requests=3, input_tokens=100, tool_calls=4),
        _row(
            "a", "LIKELY_EXPLOITABLE", "LIKELY_EXPLOITABLE", requests=None, input_tokens=None, tool_calls=None
        ),
    ]
    telemetry = cli.summarise(rows)["telemetry"]
    assert telemetry["input_tokens"] == {"reported_runs": 1, "runs": 2, "total": 100, "mean": 100.0}
    assert telemetry["output_tokens"] == {"reported_runs": 0, "runs": 2, "total": None, "mean": None}
    assert telemetry["tool_calls"]["total"] == 4 and telemetry["tool_calls"]["reported_runs"] == 1


def test_per_case_agreement_is_the_share_on_the_modal_label():
    E, N = "LIKELY_EXPLOITABLE", "LIKELY_NOT_EXPLOITABLE"
    rows = [
        _row("a", E, E, repeat=1),
        _row("a", E, E, repeat=2),
        _row("a", N, E, repeat=3),
        _row("b", N, N, repeat=1),
    ]
    by_case = {c["case"]: c for c in cli.per_case(rows)}
    assert by_case["a"]["modal_label"] == E
    assert by_case["a"]["agreement"] == pytest.approx(2 / 3)
    assert by_case["a"]["accuracy"] == pytest.approx(2 / 3)
    assert by_case["a"]["runs"] == 3
    assert by_case["b"]["agreement"] == 1.0 and by_case["b"]["accuracy"] == 1.0


def _provider(tmp_path: Path) -> Path:
    config = {
        "profiles": {"p": {"base_url": "https://llm.example.test/v1", "model_name": "model-under-test"}},
        "agents": {"producer": "p", "auditor": "p"},
    }
    path = tmp_path / "providers.json"
    path.write_text(json.dumps(config))
    return path


def test_repeats_run_each_case_n_times_and_write_the_aggregate(tmp_path, monkeypatch):
    expected_by_id = {}
    for key in _keys(DEV):
        case_dir = E2E / key
        expected_by_id[load_case(case_dir).case_id] = load_oracle(case_dir)["expected_label"]
    calls = []

    async def scripted(case, args, models, model_config):
        assert model_config["producer"]["model_name"] == "model-under-test"
        calls.append(case.case_id)
        repeat = calls.count(case.case_id)
        label = "INCONCLUSIVE" if repeat == 3 else expected_by_id[case.case_id]
        return {
            "verdict": {"label": label, "fix": "not_applicable"},
            "submissions": [],
            "run_id": f"r{len(calls)}",
        }

    class ScriptedInference:
        @asynccontextmanager
        async def models(self, config, agents=("producer", "auditor")):
            yield {name: object() for name in agents}

    monkeypatch.setattr(cli, "_investigate_one", scripted)
    code = cli.main(
        [
            "eval",
            "--set",
            str(DEV),
            "--provider",
            str(_provider(tmp_path)),
            "--repeats",
            "3",
            "--runs",
            str(tmp_path),
        ],
        inference=ScriptedInference(),
    )
    assert code == 0
    (out,) = tmp_path.glob("eval-*.json")
    summary = json.loads(out.read_text())
    assert len(calls) == 20 * 3
    assert summary["cases"] == 20 and summary["repeats"] == 3 and summary["held_out"] is False
    assert summary["models"]["producer"]["model_name"] == "model-under-test"
    assert summary["metrics"]["runs"] == 60
    assert summary["metrics"]["inconclusive_rate"] == pytest.approx(1 / 3)
    assert summary["metrics"]["accuracy"] == pytest.approx(40 / 60)
    assert len(summary["per_case"]) == 20
    assert all(c["runs"] == 3 and c["agreement"] == pytest.approx(2 / 3) for c in summary["per_case"])
    # no investigation reported usage here, so usage is unknown
    assert summary["metrics"]["telemetry"]["input_tokens"]["total"] is None
