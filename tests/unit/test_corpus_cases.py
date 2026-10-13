import json
import re
from collections import Counter
from pathlib import Path
import shutil

import pytest

from evals.corpus import cases
from evals.corpus.cases import CORPUS, HELD_OUT, agent_input, case_digest, label_words, load, snapshot, tree_digest

ROOT = Path(__file__).resolve().parents[2]


def test_every_topic_becomes_one_case_with_the_exploitable_variant_as_baseline():
    loaded = load()
    assert len(loaded) == 42 and len({case.case_id for case in loaded}) == 42
    assert Counter(case.language for case in loaded) == {"python": 22, "javascript": 9, "perl": 6, "java": 3, "c": 2}
    for case in loaded:
        if case.candidate:
            assert case.baseline.truth.expected_verdict == "potentially_exploitable"
            assert case.candidate.truth.expected_verdict == "likely_not_exploitable"
            assert case.oracle.gate.model_dump() == dict(execution="completed", finding="reproduced", fix="verified")
        else:
            assert case.oracle.gate.model_dump() == dict(execution="completed", finding="not_reproduced", fix="not_applicable")
    assert sum(case.candidate is None for case in loaded) == 2


def test_agent_input_carries_the_finding_and_baseline_files_only():
    for case in load():
        given = agent_input(case)
        paths = {source.path for source in given.source_files}
        assert case.finding.file_path in paths
        assert not label_words(given.issue) and case.finding.title in given.issue
        assert given.fixture_id == case.case_id and str(case.baseline.variant) not in given.model_dump_json()
        for word in ("potentially_exploitable", "likely_not_exploitable", "expected_verdict"):
            assert word not in given.model_dump_json()


def test_the_copy_matches_its_recorded_digest():
    assert tree_digest() in (CORPUS / "SOURCE.md").read_text()


def _copy(tmp_path: Path) -> Path:
    target = tmp_path / "corpus"
    shutil.copytree(CORPUS, target)
    return target


def test_a_label_word_in_a_variant_is_refused(tmp_path):
    target = _copy(tmp_path)
    module = target / "python/sqli/b/app.py"
    module.write_text(module.read_text() + "\n# parameterised, so this is safe\n")
    with pytest.raises(ValueError, match="label words"):
        load(target)


def test_a_pair_whose_findings_differ_beyond_location_is_refused(tmp_path):
    target = _copy(tmp_path)
    manifest = json.loads((target / "manifest.json").read_text())
    manifest["cases"][0]["finding"]["description"] += " Also check the logs."
    (target / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="differ beyond location"):
        load(target)


def test_symlinks_in_a_variant_are_refused(tmp_path):
    target = _copy(tmp_path)
    (target / "python/sqli/a/link").symlink_to("/etc/hostname")
    with pytest.raises(ValueError, match="symlink"):
        snapshot(target / "python/sqli/a")


def test_held_out_split_is_a_quarter_per_language_and_matches_its_manifest():
    loaded = load()
    held = Counter(case.language for case in loaded if case.split == "held_out")
    assert held == {language: count // 4 for language, count in Counter(c.language for c in loaded).items() if count >= 4}
    assert json.loads(HELD_OUT.read_text()) == {c.case_id: case_digest(c) for c in loaded if c.split == "held_out"}


def test_development_records_never_cite_a_held_out_corpus_case():
    held = json.loads(HELD_OUT.read_text())
    texts = [path for path in (ROOT / "docs/development").rglob("*") if path.is_file()]
    texts += [ROOT / "benchmarks/runtime-requirements.md", ROOT / "benchmarks/runtime-requirements.json"]
    cited = [(str(path), case) for path in texts for case in held
             if re.search(rf"(?<![\w-]){re.escape(case)}(?![\w-])", path.read_text(errors="replace"))]
    assert not cited


def test_runtime_report_covers_every_corpus_case_and_hides_held_out_names():
    report = json.loads((ROOT / "benchmarks/runtime-requirements.json").read_text())
    loaded = load()
    assert len(report["corpus"]) == len(loaded)
    named = {r["case_id"] for r in report["corpus"] if r["case_id"]}
    assert named == {c.case_id for c in loaded if c.split == "development"}
    assert report["inputs"]["corpus"] == "sha256:" + cases.sha256((CORPUS / "manifest.json").read_bytes()).hexdigest()
