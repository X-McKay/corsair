"""The v2 whole-chain eval set (evals/e2e/<language>/v2/, manifest evals/e2e/sets/v2.json).

No chain runs here (a whole-chain run needs Docker and live inference). These checks keep the set honest: the
counts, every input loading through v2 intake, the trees pinned by digest, Select choosing the row each oracle
names, oracles consistent with the D4 rule table, and no oracle content inside any input.
"""
import json
import re
from collections import Counter
from pathlib import Path

import pytest

from corsair import intake, matrix
from corsair.contracts import Label, TerminalReason
from corsair.rules import RULES
from evals.cases import EVALS, load_set

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "benchmarks/corpus/infosec-harness/manifest.json"
CASES = load_set("e2e", "v2")
SUPPORTED = ("python", "java", "javascript", "ruby", "perl")
RULE_LABEL = {rule.id: rule.label.value for rule in RULES}
FINDINGS = {"R0": "none", "R1": "none", "R4": "reproduced", "R5": "not_reproduced", "R6": "inconclusive"}


def _path(case) -> Path:
    return EVALS / "e2e" / case.language / "v2" / case.name / "input.json"


def _keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _keys(item)}
    return set()


def test_counts_and_metadata():
    per_language = Counter(case.language for case in CASES)
    assert all(per_language[language] >= 10 for language in SUPPORTED), per_language
    labels = Counter((case.language, case.oracle["expected_label"]) for case in CASES)
    for language in SUPPORTED:  # positives, negatives and failure modes in every supported language
        for label in ("LIKELY_EXPLOITABLE", "LIKELY_NOT_EXPLOITABLE", "UNABLE_TO_RUN"):
            assert labels[(language, label)] >= 1, (language, label)
        kinds = {case.case["kind"] for case in CASES if case.language == language}
        assert {"positive", "negative", "injection", "missing-target"} <= kinds, (language, kinds)
    for case in CASES:
        meta = case.case
        assert meta["category"] and meta["dimensions"] and "correctness" in meta["dimensions"], case.key
        assert meta["expected"].strip() and meta["probes"].strip(), case.key


@pytest.mark.parametrize("case", CASES, ids=[case.key for case in CASES])
def test_input_loads_through_v2_intake_and_pins_its_trees(case):
    loaded = intake.from_issue_json(_path(case))
    assert loaded.revision.tree_sha256 == case.oracle["revision_tree_sha256"]
    fixed = loaded.fixed_revision.tree_sha256 if loaded.fixed_revision else None
    assert fixed == case.oracle["fixed_tree_sha256"]
    row = matrix.select(loaded)
    assert (row.row_id if row else None) == case.oracle["expected_runtime_row"]


@pytest.mark.parametrize("case", CASES, ids=[case.key for case in CASES])
def test_no_oracle_content_in_input(case):
    text = _path(case).read_text()
    truth = case.oracle.get("truth", {})
    leaked = _keys(case.input) & (set(case.oracle) | set(truth.get("manifest_truth", {})) - {"source"})
    assert not leaked, (case.key, leaked)
    assert not {label.value for label in Label if label.value in text}, case.key
    assert "expected" not in text and "oracle" not in text
    if "manifest_case" in truth:
        assert truth["manifest_case"] not in text  # manifest names carry the answer
    # A case id that names the behaviour (target-absent, ...) carries the answer; such cases let intake assign one.
    assert "case_id" not in case.input or re.fullmatch(r"[a-z0-9-]+-[a-z]", case.name), case.key


@pytest.mark.parametrize("case", CASES, ids=[case.key for case in CASES])
def test_oracle_agrees_with_the_rule_table(case):
    oracle = case.oracle
    labels = {label.value for label in Label}
    assert oracle["expected_label"] in oracle["acceptable_labels"]
    assert set(oracle["acceptable_labels"]) <= labels and set(oracle["forbidden_labels"]) <= labels
    assert not set(oracle["acceptable_labels"]) & set(oracle["forbidden_labels"])
    rule = oracle["expected_rule"]
    if rule is not None:
        assert RULE_LABEL[rule] == oracle["expected_label"]
        assert oracle["expected_finding"] == FINDINGS[rule]
        TerminalReason(oracle["expected_terminal_reason"])
    fixed = case.input.get("fixed_source") is not None
    if not fixed:
        assert oracle["expected_fix"] == "not_applicable"
    elif rule is not None:
        assert oracle["expected_fix"] == ("verified" if rule == "R4" else "not_verified")
    if oracle["expected_runtime_row"] is None:  # Select stops the chain: R0 no_runtime is fully determined
        assert (rule, oracle["expected_terminal_reason"]) == ("R0", "no_runtime")


def test_corpus_cases_match_the_manifest_route():
    """A case built from the manifest is the same Case `corsair-v2 run --case` builds (finding, tree, id)."""
    corpus = [case for case in CASES if case.input.get("case_id", "").startswith("corpus:")]
    assert corpus
    for case in corpus:
        name, manifest = case.oracle["truth"]["manifest_case"], ROOT / case.oracle["truth"]["manifest"]
        expected = intake.load_corpus_case(manifest, name)
        loaded = intake.from_issue_json(_path(case))
        assert (loaded.case_id, loaded.finding, loaded.revision) == (
            expected.case_id, expected.finding, expected.revision), case.key
        assert intake.load_oracle(manifest, name)["expected_label"] in (
            case.oracle["expected_label"], *case.oracle["acceptable_labels"]) or case.oracle[
            "expected_terminal_reason"] == "no_runtime", case.key


def test_no_held_out_family_is_used():
    held = set(json.loads((ROOT / "evals/corpus/held_out.json").read_text()))
    entries = {entry["name"]: entry for entry in json.loads(MANIFEST.read_text())["cases"]}
    for case in CASES:
        texts = [_path(case).read_text(), json.dumps(case.case), json.dumps(case.oracle)]
        assert not any(re.search(rf"{re.escape(family)}(?![a-z0-9])", text) for family in held for text in texts), \
            case.key
        name = case.oracle.get("truth", {}).get("manifest_case")
        if name is not None and ROOT / case.oracle["truth"]["manifest"] == MANIFEST:
            _, language, topic, _ = entries[name]["finding"]["repo_url"].split("/")
            assert f"ih-{language}-{topic}" not in held
