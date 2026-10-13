"""IDEA-0005 step 1 guards: the inventory stays whole, manifests agree with it, agent text names no answer key."""
import csv
import json
import shutil

import pytest
import yaml

from evals.benchmark.cases import CASES, DEFAULT_BLOCKING, INVENTORY, agent_input, load, load_inventory
from evals.benchmark.report import counts, markdown

JSPWIKI = CASES / "jspwiki-forwarding"


def test_csv_and_json_inventories_agree_row_for_row():
    rows = list(csv.DictReader((INVENTORY.parent / "candidate-cases.csv").open(newline="")))
    cases = load_inventory().cases
    assert len(rows) == len(cases) == 50
    for row, case in zip(rows, cases):
        for column, value in row.items():
            expected = getattr(case, column)
            assert value == ("" if expected is None else str(expected)), (case.case_id, column)


def test_every_row_is_kept_and_the_jspwiki_manifest_is_joined():
    entries = load()
    assert [entry.inventory.case_id for entry in entries] == [case.case_id for case in load_inventory().cases]
    joined = {entry.inventory.case_id: entry for entry in entries if entry.manifest}
    assert set(joined) == {"VUL4J-18"}
    assert joined["VUL4J-18"].directory == JSPWIKI and joined["VUL4J-18"].admission == "not_admitted"
    assert {entry.inventory.language for entry in entries} == set(DEFAULT_BLOCKING)


def test_agent_input_carries_no_evaluator_label():
    entry = next(entry for entry in load() if entry.manifest)
    visible = agent_input(entry).model_dump_json()
    row = entry.inventory
    evaluator = entry.manifest.evaluator
    labels = (row.case_id, row.issue_id, row.source, row.cwe, evaluator.fix_reference, evaluator.reference_test.sha256)
    for label in labels:
        assert label not in visible


def _cases(tmp_path, change):
    directory = tmp_path / "cases" / "jspwiki-forwarding"
    shutil.copytree(JSPWIKI, directory)
    manifest = yaml.safe_load((directory / "case.yaml").read_text())
    change(manifest, directory)
    (directory / "case.yaml").write_text(yaml.safe_dump(manifest))
    return tmp_path / "cases"


def _set(part, key, value):
    return lambda manifest, directory: manifest[part].__setitem__(key, value)


@pytest.mark.parametrize("change, message", [
    (_set("evaluator", "case_id", "VUL4J-0"), "unknown case id"),
    (_set("agent", "repository", "https://github.com/apache/jspwiki-fork"), "repository differs"),
    (_set("agent", "candidate", "f140a2a4371735ad24d04a1d78c6e1d9ceaed76f"), "fix commit differs"),
    (_set("agent", "build_system", "Gradle"), "build system differs"),
    (_set("evaluator", "cwe", "CWE-79"), "CWE differs"),
    (lambda manifest, directory: (directory / "BenchmarkWikiServletForwardingTest.java").write_text("changed"),
     "digest differs"),
    (_set("evaluator", "reference_test", {"path": "../README.md", "sha256": "0" * 64}), "confined"),
    (_set("evaluator", "blocking", ["G99"]), "blocking"),
    (_set("agent", "baseline", "main"), "baseline"),
    (_set("evaluator", "admission", "admitted"), "admitted requires"),
])
def test_inconsistent_manifests_are_refused(tmp_path, change, message):
    with pytest.raises(ValueError, match=message):
        load(cases=_cases(tmp_path, change))


@pytest.mark.parametrize("leak", ["VUL4J-18", "vul4j-18", "CVE-2019-0225", "cve-2021-0001", "GHSA-4rvg-955w-h68q",
                                  "the Vul4J dataset", "a SecBench.js record"])
def test_agent_issue_text_naming_the_answer_key_is_refused(tmp_path, leak):
    change = lambda manifest, directory: manifest["agent"].__setitem__("issue", f"Forwarding issue, see {leak}.")
    with pytest.raises(ValueError, match="names"):
        load(cases=_cases(tmp_path, change))


def test_a_second_manifest_for_one_case_is_refused(tmp_path):
    cases = _cases(tmp_path, lambda manifest, directory: None)
    shutil.copytree(cases / "jspwiki-forwarding", cases / "jspwiki-copy")
    with pytest.raises(ValueError, match="second manifest"):
        load(cases=cases)


def test_report_counts_cover_the_whole_denominator():
    report = counts(load())
    assert report["total"] == 50
    for name in ("language", "build_system", "cwe", "manifest", "admission"):
        assert sum(report["by"][name].values()) == 50, name
    assert report["by"]["language"] == {"Java": 10, "JavaScript": 10, "Perl": 10, "Python": 10, "Ruby": 10}
    assert report["by"]["manifest"] == {"absent": 49, "present": 1}
    assert report["by"]["admission"] == {"not_admitted": 50}
    assert report["by"]["cwe"]["unrecorded"] == 40
    assert all(0 < count <= 50 for count in report["by"]["blocking"].values())
    assert report["by"]["blocking"]["G2"] == 49  # the manifest meets G2 for JSPWiki only
    assert json.loads(json.dumps(report)) == report and "| language | Java | 10 |" in markdown(report)


@pytest.mark.parametrize("commit", ["x" + "a" * 40, "a" * 40 + "\n", "a" * 41])
def test_commit_fields_require_exactly_forty_hex_characters(commit):
    from pydantic import ValidationError
    from evals.benchmark.cases import AgentPart
    good = dict(issue="i", scope="component", repository="https://github.com/o/r", baseline="a" * 40,
                candidate="b" * 40, language="Java", build_system="Maven")
    AgentPart(**good)
    for field in ("baseline", "candidate"):
        with pytest.raises(ValidationError):
            AgentPart(**good | {field: commit})


def test_unmeasured_execution_limits_stay_visible_in_the_report():
    blocked = counts(load())["by"]["blocking"]
    assert blocked["G13"] == 50


def test_identification_corpus_uses_the_reviewed_issue_text():
    corpus = yaml.safe_load((CASES.parents[1] / "evals/repository_identification/cases.yaml").read_text())
    jspwiki = next(e for e in load() if e.manifest and e.manifest.evaluator.case_id == "VUL4J-18")
    assert corpus["cases"][0]["inputs"]["issue"] == jspwiki.manifest.agent.issue
