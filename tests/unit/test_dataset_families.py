"""Family-grouped splits: manifest membership checks and per-family report views.

The manifests here are synthetic and are never loaded as frozen requests: the split check
reads membership only, so digests are placeholders and no request or oracle file exists.
"""

import json
import sys
from pathlib import Path

import pytest

from corsair.contracts import digest
from corsair.evaluation import families
from corsair.evaluation.comparison import compare_reports
from corsair.evaluation.families import (
    Member,
    chain_pair,
    check_family_splits,
    dataset_members,
    family_deltas,
    family_view,
    label_report,
    label_rows,
    split_violations,
)
from corsair.evaluation.scoring import Dataset

ROOT = Path(__file__).resolve().parents[2]
PLACEHOLDER = "0" * 64


def entry(case_id: str, family: str, split: str, request: str | None = None) -> dict:
    return {
        "case_id": case_id,
        "family": family,
        "split": split,
        "request": request or f"fixtures/{case_id}/request.json",
        "oracle": f"fixtures/{case_id}/oracle.json",
        "request_digest": PLACEHOLDER,
        "oracle_digest": PLACEHOLDER,
    }


def manifest(path: Path, *entries: dict) -> Path:
    path.write_text(json.dumps({"schema_version": "corsair.dataset/1", "entries": list(entries)}))
    return path


def rules(result: dict) -> list[tuple[str, str]]:
    return [
        (item["rule"], item.get("family") or item.get("pair") or item["case_id"])
        for item in result["violations"]
    ]


# Split check


def test_a_clean_family_grouped_split_passes(tmp_path):
    dev = manifest(
        tmp_path / "dev.json",
        entry("cmdi-a", "ih-python-cmdi", "dev", "datasets/chain/python/cmdi-a/request.json"),
        entry("cmdi-b", "ih-python-cmdi", "dev", "datasets/chain/python/cmdi-b/request.json"),
    )
    held = manifest(
        tmp_path / "held.json",
        entry("sqli-a", "ih-python-sqli", "held_out", "datasets/chain/python/sqli-a/request.json"),
        entry("sqli-b", "ih-python-sqli", "held_out", "datasets/chain/python/sqli-b/request.json"),
    )

    result = check_family_splits([dev, held])

    assert result["ok"] is True
    assert result["violations"] == []
    assert result["families"] == 2
    assert [item["splits"] for item in result["datasets"]] == [["dev"], ["held_out"]]


def test_a_family_in_both_dev_and_held_out_fails(tmp_path):
    dev = manifest(tmp_path / "dev.json", entry("case01", "family01", "dev"))
    held = manifest(tmp_path / "held.json", entry("case09", "family01", "held_out"))

    result = check_family_splits([dev, held])

    assert result["ok"] is False
    assert rules(result) == [("family_crosses_splits", "family01")]
    assert result["violations"][0]["splits"] == {
        "dev": ["dev.json:case01"],
        "held_out": ["held.json:case09"],
    }


def test_a_chain_pair_split_across_dev_and_held_out_fails_even_with_distinct_families(tmp_path):
    # Distinct family labels hide the leak from the family rule; the pair rule still sees
    # that the two variants of one chain row share a parent directory and class stem.
    dev = manifest(
        tmp_path / "dev.json",
        entry("cmdi-a", "cmdi-vulnerable", "dev", "datasets/chain/python/cmdi-a/request.json"),
    )
    held = manifest(
        tmp_path / "held.json",
        entry("cmdi-b", "cmdi-fixed", "held_out", "datasets/chain/python/cmdi-b/request.json"),
    )

    result = check_family_splits([dev, held])

    assert result["ok"] is False
    assert rules(result) == [
        ("pair_crosses_splits", "datasets/chain/python/cmdi"),
        ("pair_crosses_families", "datasets/chain/python/cmdi"),
    ]


def test_a_case_in_two_splits_fails(tmp_path):
    dev = manifest(tmp_path / "dev.json", entry("case01", "family01", "dev"))
    held = manifest(tmp_path / "held.json", entry("case01", "family02", "held_out"))

    assert ("case_crosses_splits", "case01") in rules(check_family_splits([dev, held]))


def test_the_same_case_in_one_split_across_files_is_not_a_violation(tmp_path):
    dev = manifest(tmp_path / "dev.json", entry("case01", "family01", "dev"))
    expanded = manifest(tmp_path / "dev-expanded.json", entry("case01", "family01", "dev"))

    assert check_family_splits([dev, expanded])["ok"] is True


def test_unlabelled_members_are_counted_but_never_contradict_a_split():
    members = [
        Member("agent.json", "case01", None, None, None),
        Member("dev.json", "case01", "family01", "dev", None),
    ]

    assert split_violations(members) == []


@pytest.mark.parametrize(
    "path,pair",
    [
        ("datasets/chain/python/cmdi-a/request.json", "datasets/chain/python/cmdi"),
        (
            "datasets/chain/java/spring-security-b/request.json",
            "datasets/chain/java/spring-security",
        ),
        ("datasets/chain/python/ineffective-fix/request.json", None),
        ("fixtures/case01/request.json", None),
    ],
)
def test_chain_pair_is_read_from_the_variant_directory(path, pair):
    assert chain_pair(path) == pair


def test_agent_datasets_are_unlabelled_and_legacy_listings_take_their_file_stem(tmp_path):
    agent = tmp_path / "producer.json"
    agent.write_text(
        json.dumps(
            {
                "schema_version": "corsair.agent-dataset/1",
                "entries": [{"case_id": "case01", "input": "fixtures/case01/request.json"}],
            }
        )
    )
    listing = tmp_path / "held_out.json"
    listing.write_text(json.dumps({"ih-python-sqli": PLACEHOLDER}))

    assert dataset_members(agent) == [Member("producer.json", "case01", None, None, None)]
    assert dataset_members(listing) == [
        Member("held_out.json", "ih-python-sqli", "ih-python-sqli", "held_out", None)
    ]
    assert check_family_splits([agent, listing])["unlabelled_entries"] == 1


@pytest.mark.parametrize(
    "body",
    [
        [],
        {"schema_version": "other/1"},
        {"family": "not-a-digest"},
        {"schema_version": "corsair.agent-dataset/1", "entries": [{"case_id": "c"}]},
    ],
)
def test_an_unsupported_manifest_is_refused(tmp_path, body):
    path = tmp_path / "unknown.json"
    path.write_text(json.dumps(body))

    with pytest.raises(ValueError, match=r"unknown\.json"):
        dataset_members(path)


def test_checked_in_dataset_families_keep_one_split():
    paths = sorted((ROOT / "evals/datasets").glob("*.json"))

    result = check_family_splits(paths)

    assert result["ok"] is True, result["violations"]
    splits = {split for item in result["datasets"] for split in item["splits"]}
    assert {"dev", "held_out", "safety", "adversarial"} <= splits


def test_the_module_entrypoint_exits_by_violation_and_names_a_remedy(tmp_path, monkeypatch, capsys):
    clean = manifest(tmp_path / "dev.json", entry("case01", "family01", "dev"))
    leak = manifest(tmp_path / "held.json", entry("case09", "family01", "held_out"))

    for argv, code in (([clean], 0), ([clean, leak], 1), ([tmp_path / "absent.json"], 2)):
        monkeypatch.setattr(sys, "argv", ["families", *map(str, argv)])
        with pytest.raises(SystemExit) as stopped:
            families.main()
        assert stopped.value.code == code
    captured = capsys.readouterr()
    assert "Remedy:" in captured.err
    assert '"family_crosses_splits"' in captured.out


# Row labels and family views


def _row(case_id, *, status="pass", verdict="EXPLOIT_DEMONSTRATED", **fields):
    return {
        "run_id": f"run-{case_id}",
        "case_id": case_id,
        "status": status,
        "verdict": verdict,
        "disposition": "SUPPORTED",
        "execution_status": "COMPLETED",
        "forbidden_label": False,
        "llm_calls": 2,
        **fields,
    }


def test_label_rows_adds_the_declared_family_and_split_only_to_known_cases():
    dataset = Dataset.model_validate(
        {"entries": [entry("case01", "family01", "dev"), entry("case02", "family02", "dev")]}
    )
    rows = [_row("case01"), {"run_id": "missing", "status": "unavailable"}, _row("other")]

    labelled = label_rows(rows, dataset)

    assert (labelled[0]["family"], labelled[0]["split"]) == ("family01", "dev")
    assert labelled[1] == rows[1] and labelled[2] == rows[2]
    assert "family" not in rows[0]


def test_label_report_refuses_a_manifest_the_report_was_not_scored_against(tmp_path):
    path = manifest(tmp_path / "dev.json", entry("case01", "family01", "dev"))
    dataset = Dataset.model_validate_json(path.read_bytes())
    report = {"rows": [_row("case01")], "summary": {}, "dataset_digest": digest(dataset)}

    assert label_report(report, path)["rows"][0]["family"] == "family01"
    with pytest.raises(ValueError, match="differs from the report's dataset digest"):
        label_report({**report, "dataset_digest": PLACEHOLDER}, path)


def test_family_view_reports_pass_decisive_and_forbidden_labels_per_family_and_split():
    rows = [
        _row("cmdi-a", family="cmdi", split="dev"),
        _row("cmdi-b", status="fail", verdict="INCONCLUSIVE", family="cmdi", split="dev"),
        _row("sqli-a", forbidden_label=True, status="fail", family="sqli", split="held_out"),
        _row("sqli-a", verdict="EXPLOIT_NOT_DEMONSTRATED", family="sqli", split="held_out"),
        {"case_id": "lost", "run_id": "lost", "status": "unavailable"},
    ]

    view = family_view(rows)

    by_family = {item["family"]: item for item in view["families"]}
    assert [item["family"] for item in view["families"]] == ["cmdi", "sqli", None]
    assert by_family["cmdi"]["splits"] == ["dev"]
    assert (by_family["cmdi"]["cases"], by_family["cmdi"]["attempts"]) == (2, 2)
    assert (by_family["cmdi"]["passed"], by_family["cmdi"]["pass_rate"]) == (1, 0.5)
    assert (by_family["cmdi"]["decisive"], by_family["cmdi"]["decisive_rate"]) == (1, 0.5)
    assert (by_family["sqli"]["cases"], by_family["sqli"]["decisive"]) == (1, 2)
    assert by_family["sqli"]["forbidden_labels"] == 1
    assert by_family[None]["unavailable_results"] == 1
    assert by_family[None]["decisive"] is None
    by_split = {item["split"]: item for item in view["splits"]}
    assert (by_split["dev"]["families"], by_split["held_out"]["families"]) == (1, 1)
    assert by_split["held_out"]["pass_rate"] == 0.5


def test_isolated_agent_rows_have_no_decisive_count():
    rows = [{"case_id": "case01", "status": "pass", "match_kind": "exact_match"}]

    (group,) = family_view(rows)["families"]

    assert group["family"] is None
    assert group["decisive"] is None and group["decisive_rate"] is None


def test_compare_attributes_cases_regressions_and_family_deltas():
    digest_value = "sha256:frozen"
    before = [_row("cmdi-a", family="cmdi"), _row("sqli-a", family="sqli")]
    after = [
        _row("cmdi-a", family="cmdi"),
        _row(
            "sqli-a",
            status="fail",
            forbidden_label=True,
            verdict="EXPLOIT_DEMONSTRATED",
            family="sqli",
        ),
    ]
    baseline = {"rows": before, "summary": {}, "dataset_digest": digest_value}
    candidate = {"rows": after, "summary": {}, "dataset_digest": digest_value}

    diff = compare_reports(baseline, candidate)
    deltas = {item["family"]: item for item in family_deltas(before, after, diff["regressions"])}

    assert {case["case_id"]: case["family"] for case in diff["cases"]} == {
        "cmdi-a": "cmdi",
        "sqli-a": "sqli",
    }
    assert {(item["family"], item["reason"]) for item in diff["regressions"]} == {
        ("sqli", "pass_to_fail"),
        ("sqli", "new_forbidden_label"),
    }
    assert deltas["cmdi"]["regressions"] == 0 and deltas["cmdi"]["pass_rate_delta"] == 0
    assert deltas["sqli"]["regressions"] == 2
    assert deltas["sqli"]["pass_rate_delta"] == -1
    assert deltas["sqli"]["forbidden_labels_delta"] == 1


def test_a_family_present_on_one_side_has_unknown_deltas():
    deltas = family_deltas([_row("a", family="old")], [_row("b", family="new")], [])

    by_family = {item["family"]: item for item in deltas}
    assert by_family["old"]["candidate"] is None and by_family["new"]["baseline"] is None
    assert by_family["old"]["pass_rate_delta"] is None
