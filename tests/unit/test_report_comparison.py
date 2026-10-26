"""Unit tests for case-by-case comparison of saved evaluation reports."""

import json

import pytest

from corsair.evaluation.comparison import compare_reports, read_report

DIGEST = "sha256:frozen-dataset"


def row(case_id, status="pass", verdict="EXPLOIT_DEMONSTRATED", **fields):
    return {
        "run_id": f"run-{case_id}",
        "case_id": case_id,
        "status": status,
        "verdict": verdict,
        "execution_status": "COMPLETED",
        "forbidden_label": False,
        "llm_calls": 4,
        "tool_calls": 2,
        "input_tokens": 100,
        "output_tokens": 20,
        "agent_seconds": 1.5,
        "config_digest": "config-a",
        **fields,
    }


def report(*rows, dataset_digest=DIGEST):
    value = {"rows": list(rows), "summary": {"attempts": len(rows)}}
    if dataset_digest is not None:
        value["dataset_digest"] = dataset_digest
    return value


def reasons(diff):
    return [(item["case_id"], item["repeat"], item["reason"]) for item in diff["regressions"]]


def test_identical_reports_have_no_regression_and_zero_deltas():
    baseline = report(row("case01"), row("case02", status="fail", verdict="INCONCLUSIVE"))

    diff = compare_reports(baseline, baseline)

    assert diff["regression"] is False
    assert diff["dataset_match"] is True
    assert diff["regressions"] == []
    assert diff["counts"]["joined"] == 2
    assert all(case["flip"] is None and not case["label_changed"] for case in diff["cases"])
    assert diff["summary_delta"]["pass_rate"] == {"baseline": 0.5, "candidate": 0.5, "delta": 0}
    assert diff["summary_delta"]["agent_seconds"]["delta"] == 0
    assert diff["config_digests"] == {"baseline": ["config-a"], "candidate": ["config-a"]}


def test_an_improvement_is_a_fail_to_pass_flip_and_not_a_regression():
    baseline = report(row("case01", status="fail", verdict="INCONCLUSIVE"))
    candidate = report(row("case01", llm_calls=6, agent_seconds=1.0))

    diff = compare_reports(baseline, candidate)

    (case,) = diff["cases"]
    assert diff["regression"] is False
    assert case["flip"] == "fail_to_pass"
    assert case["label_changed"] is True
    assert (case["baseline_label"], case["candidate_label"]) == (
        "INCONCLUSIVE",
        "EXPLOIT_DEMONSTRATED",
    )
    assert case["usage_delta"]["llm_calls"] == 2
    assert case["usage_delta"]["agent_seconds"] == -0.5
    assert diff["summary_delta"]["passed"]["delta"] == 1


def test_a_pass_that_becomes_fail_or_unavailable_regresses():
    baseline = report(row("case01"), row("case02"))
    candidate = report(
        row("case01", status="fail", verdict="EXPLOIT_NOT_DEMONSTRATED"),
        {"case_id": "case02", "run_id": "run-case02", "status": "unavailable"},
    )

    diff = compare_reports(baseline, candidate)

    assert diff["regression"] is True
    assert reasons(diff) == [("case01", 0, "pass_to_fail"), ("case02", 0, "pass_to_fail")]
    assert diff["cases"][1]["usage_delta"]["llm_calls"] is None


def test_a_new_forbidden_label_regresses_even_when_the_case_already_failed():
    baseline = report(row("case01", status="fail", verdict="INCONCLUSIVE"))
    candidate = report(
        row("case01", status="fail", verdict="EXPLOIT_NOT_DEMONSTRATED", forbidden_label=True)
    )

    diff = compare_reports(baseline, candidate)

    assert diff["regression"] is True
    assert reasons(diff) == [("case01", 0, "new_forbidden_label")]
    assert diff["counts"]["new_forbidden_labels"] == 1


def test_a_forbidden_label_already_present_in_the_baseline_is_not_new():
    forbidden = row(
        "case01", status="fail", verdict="EXPLOIT_NOT_DEMONSTRATED", forbidden_label=True
    )

    assert compare_reports(report(forbidden), report(forbidden))["regression"] is False


def test_mismatched_dataset_digests_are_refused_without_explicit_permission():
    baseline = report(row("case01"))
    candidate = report(row("case01"), dataset_digest="sha256:another-dataset")

    with pytest.raises(ValueError, match="different or undeclared dataset digests"):
        compare_reports(baseline, candidate)

    diff = compare_reports(baseline, candidate, allow_dataset_mismatch=True)
    assert diff["dataset_match"] is False
    assert diff["dataset_digest"] == {"baseline": DIGEST, "candidate": "sha256:another-dataset"}
    assert diff["regression"] is False


def test_an_undeclared_dataset_digest_is_never_treated_as_a_match():
    undeclared = report(row("case01"), dataset_digest=None)

    with pytest.raises(ValueError, match="undeclared"):
        compare_reports(undeclared, undeclared)
    assert (
        compare_reports(undeclared, undeclared, allow_dataset_mismatch=True)["dataset_match"]
        is False
    )


def test_missing_candidate_cases_regress_and_new_cases_are_listed():
    baseline = report(row("case01"), row("case02"))
    candidate = report(row("case01"), row("case03"))

    diff = compare_reports(baseline, candidate)

    presence = {case["case_id"]: case["presence"] for case in diff["cases"]}
    assert presence == {"case01": "both", "case02": "baseline_only", "case03": "candidate_only"}
    assert reasons(diff) == [("case02", 0, "missing_in_candidate")]
    assert diff["counts"]["missing_in_candidate"] == 1
    assert diff["counts"]["new_in_candidate"] == 1


def test_repeats_join_by_ordinal_or_explicit_repeat_index():
    baseline = report(row("case01"), row("case01", status="fail", verdict="INCONCLUSIVE"))
    candidate = report(row("case01"), row("case01"))

    diff = compare_reports(baseline, candidate)
    assert [(case["repeat"], case["flip"]) for case in diff["cases"]] == [
        (0, None),
        (1, "fail_to_pass"),
    ]

    isolated = report(
        row("case01", repeat=1, verdict=None, match_kind="CONTROL_MISMATCH", status="fail"),
        row("case01", repeat=0, verdict=None, match_kind="EXACT_MATCH"),
    )
    swapped = report(
        row("case01", repeat=0, verdict=None, match_kind="EXACT_MATCH"),
        row("case01", repeat=1, verdict=None, match_kind="EXACT_MATCH"),
    )
    diff = compare_reports(isolated, swapped)
    assert [(case["repeat"], case["candidate_label"]) for case in diff["cases"]] == [
        (0, "EXACT_MATCH"),
        (1, "EXACT_MATCH"),
    ]
    assert diff["cases"][1]["flip"] == "fail_to_pass"


def test_duplicate_explicit_repeat_is_rejected():
    duplicated = report(row("case01", repeat=0), row("case01", repeat=0))

    with pytest.raises(ValueError, match="repeats case case01 attempt 0"):
        compare_reports(duplicated, duplicated)


def test_unknown_usage_keeps_deltas_and_totals_unknown():
    baseline = report(row("case01"))
    candidate = report(row("case01", input_tokens=None, agent_seconds=None))

    diff = compare_reports(baseline, candidate)

    usage = diff["cases"][0]["usage_delta"]
    assert usage["input_tokens"] is None and usage["agent_seconds"] is None
    assert usage["llm_calls"] == 0
    assert diff["summary_delta"]["input_tokens"] == {
        "baseline": 100,
        "candidate": None,
        "delta": None,
    }


def test_new_rows_without_case_identity_regress():
    baseline = report(row("case01"))
    candidate = report(row("case01"), {"run_id": "lost", "status": "unavailable"})

    diff = compare_reports(baseline, candidate)

    assert diff["unidentified_rows"] == {"baseline": 0, "candidate": 1}
    assert reasons(diff) == [(None, None, "unidentified_rows")]


def test_compare_requires_per_case_rows():
    with pytest.raises(ValueError, match="per-case rows"):
        compare_reports({"summary": {}, "dataset_digest": DIGEST}, report(row("case01")))


def test_read_report_validates_summary_and_rows(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report(row("case01"))))
    assert read_report(path)["rows"][0]["case_id"] == "case01"

    path.write_text(json.dumps({"rows": []}))
    with pytest.raises(ValueError, match="summary object"):
        read_report(path)
    path.write_text(json.dumps({"summary": {}, "rows": ["not-a-row"]}))
    with pytest.raises(ValueError, match="list of objects"):
        read_report(path)
