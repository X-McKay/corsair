"""Intake: corpus cases without truth, oracles for evaluators, generic request files, and the tree digest."""
import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from corsair import intake
from corsair.contracts import Label

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "benchmarks/corpus/infosec-harness/manifest.json"
CASES = json.loads(MANIFEST.read_text())["cases"]


@pytest.mark.parametrize("entry", CASES, ids=[c["name"] for c in CASES])
def test_every_corpus_case_loads_without_truth(entry):
    case = intake.load_corpus_case(MANIFEST, entry["name"])
    assert case.case_id == intake.corpus_case_id(entry["name"]) and entry["name"] not in case.model_dump_json()
    assert Path(case.revision.source) == (MANIFEST.parent / entry["finding"]["repo_url"].removeprefix("eval-corpus/"))
    assert Path(case.revision.source).is_dir()
    finding = entry["finding"]
    assert (case.finding.title, case.finding.file_path, case.finding.start_line, case.finding.cwe) == (
        finding["title"], finding["file_path"], finding["start_line"], finding["cwe"])
    # The maintainer's name can read "unreachable"; the case carries only its digest.
    dumped = case.model_dump_json()
    for key in ("truth", "expected_verdict", "reachability", "sink_file", "sink_line", "target_callable"):
        assert key not in dumped
    for key in ("expected_verdict", "reachability"):
        assert entry["truth"][key] not in dumped


def test_oracle_maps_expected_labels():
    vulnerable = intake.load_oracle(MANIFEST, "sqli-vulnerable")
    fixed = intake.load_oracle(MANIFEST, "sqli-fixed")
    assert vulnerable["expected_label"] == Label.LIKELY_EXPLOITABLE.value
    assert fixed["expected_label"] == Label.LIKELY_NOT_EXPLOITABLE.value
    assert vulnerable["target_callable"] == "get_user" and vulnerable["sink_line"] == 16


def test_unknown_case_is_refused():
    with pytest.raises(KeyError):
        intake.load_corpus_case(MANIFEST, "no-such-case")


def test_tree_digest_is_content_mode_and_path_sensitive(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a/x.py").write_text("print(1)\n")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git/HEAD").write_text("ref")
    first = intake.tree_sha256(tmp_path)
    (tmp_path / ".git/HEAD").write_text("other")
    assert intake.tree_sha256(tmp_path) == first  # .git is not part of the tree
    os.chmod(tmp_path / "a/x.py", 0o755)
    executable = intake.tree_sha256(tmp_path)
    assert executable != first
    os.chmod(tmp_path / "a/x.py", 0o700)
    assert intake.tree_sha256(tmp_path) == executable  # modes are normalised, not raw
    (tmp_path / "a/x.py").write_text("print(2)\n")
    assert intake.tree_sha256(tmp_path) != executable
    (tmp_path / "link").symlink_to("a")
    assert intake.tree_sha256(tmp_path) != executable


def test_issue_json(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/app.py").write_text("x = 1\n")
    request = {"finding": {"title": "SQL injection", "file_path": "app.py", "start_line": 1, "cwe": "CWE-89"},
               "source": "src", "fixed_source": "src"}
    path = tmp_path / "issue.json"
    path.write_text(json.dumps(request))
    case = intake.from_issue_json(path)
    assert case.case_id.startswith("issue:") and case.finding.cwe == "CWE-89"
    assert case.revision.source == str((tmp_path / "src").resolve())
    assert case.fixed_revision is not None and case.fixed_revision.tree_sha256 == case.revision.tree_sha256
    path.write_text(json.dumps({**request, "case_id": "ticket-7", "fixed_source": None}))
    assert intake.from_issue_json(path).case_id == "ticket-7"
    path.write_text(json.dumps({**request, "truth": {"expected_verdict": "potentially_exploitable"}}))
    with pytest.raises(ValidationError):
        intake.from_issue_json(path)
