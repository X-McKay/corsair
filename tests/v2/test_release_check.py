"""tools/release_check.py: the prepared release check and enabling gate, offline, against a real scripted run."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

from evals import run as eval_run

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("release_check", ROOT / "tools/release_check.py")
release_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_check)


@pytest.fixture(scope="module")
def grounding_summary(tmp_path_factory):
    """A real scripted grounding run's summary, relabelled as the live run a person would commit, in the committed
    baseline's shape (``evals/run.py --commit-baseline`` keeps the rollups and drops the attempt rows)."""
    results = tmp_path_factory.mktemp("results")
    assert eval_run.main(["grounding", "--results", str(results)]) == 0
    (run,) = [path for path in (results / "grounding").iterdir() if path.is_dir()]
    summary = json.loads((run / "summary.json").read_text())
    summary["mode"] = summary["identity"]["mode"] = "live"
    summary["identity"]["provider"] = {"grounding": {"profile": "local"}}
    return {key: value for key, value in summary.items() if key != "attempts"}


@pytest.fixture
def isolated(tmp_path, monkeypatch, grounding_summary):
    """Baselines and an enforced policy under tmp_path; the agent's identity and dataset digest stay real."""
    monkeypatch.setattr(release_check, "baseline_path", lambda agent, name: tmp_path / agent / f"{name}-live.json")
    policy = yaml.safe_load(release_check.policy_path("grounding").read_text())
    policy["enforced"] = True
    policy["applies_to"] = {"sets": ["development"], "mode": "live"}
    path = tmp_path / "release-policy.yaml"
    path.write_text(yaml.safe_dump(policy))
    monkeypatch.setattr(release_check, "policy_path", lambda agent: path)

    def commit(summary, thresholds=None):
        if thresholds is not None:
            policy["thresholds"] = thresholds
            path.write_text(yaml.safe_dump(policy))
        target = tmp_path / "grounding" / "development-live.json"
        target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps(summary))
    return commit


def proposed(capsys):
    assert release_check.propose("grounding") == 0
    text = capsys.readouterr().out
    return yaml.safe_load(text.split("\n", 1)[1])["thresholds"]


def test_no_baseline_fails(isolated):
    status, reasons = release_check.check_one("grounding", "development")
    assert status == "fail" and reasons[0].startswith("no committed live baseline")


def test_a_current_baseline_passes_the_thresholds_proposed_from_it(isolated, grounding_summary, capsys):
    isolated(grounding_summary)
    thresholds = proposed(capsys)
    assert thresholds["accuracy"] and all(rule["min"] is not None for rule in thresholds["accuracy"].values())
    isolated(grounding_summary, thresholds)
    # a scripted run never exhausts a budget, but records no status per attempt; a live one does
    summary = copy.deepcopy(grounding_summary)
    overall = summary["rollups"]["all"]
    overall["statuses"], overall["status_unreported"] = {"ok": overall["attempts"]}, 0
    isolated(summary)
    assert release_check.check_one("grounding", "development") == ("pass", [])


def test_unset_thresholds_and_a_deferred_policy_fail(isolated, grounding_summary, tmp_path):
    isolated(grounding_summary)
    status, reasons = release_check.check_one("grounding", "development")
    assert status == "fail" and any("not_set" in reason for reason in reasons)
    policy = yaml.safe_load((tmp_path / "release-policy.yaml").read_text())
    (tmp_path / "release-policy.yaml").write_text(yaml.safe_dump(policy | {"enforced": False}))
    assert "release policy is not enforced (enforced: false)" in release_check.check_one("grounding", "development")[1]


def test_a_baseline_of_another_prompt_or_dataset_is_stale(isolated, grounding_summary):
    summary = copy.deepcopy(grounding_summary)
    summary["identity"]["prompt_version"] = "an-older-prompt"
    summary["identity"]["dataset_sha256"] = "0" * 64
    isolated(summary)
    stale = [reason for reason in release_check.check_one("grounding", "development")[1] if "different agent" in reason]
    assert stale == ["baseline measured a different agent: dataset_sha256, prompt_version"]


def test_a_scripted_or_narrowed_run_is_never_a_release_baseline(isolated, grounding_summary):
    summary = copy.deepcopy(grounding_summary) | {"mode": "scripted", "language": "python"}
    isolated(summary)
    reasons = release_check.check_one("grounding", "development")[1]
    assert "baseline mode is 'scripted', not live" in reasons and "baseline is a language-narrowed run" in reasons


def language(exploitable=(1, 1), safe=(1, 1)):
    """A per-language rollup's dispositions: (passed, total) per expected label."""
    per_label = {label: {"passed": passed, "total": total}
                 for label, (passed, total) in (("LIKELY_EXPLOITABLE", exploitable), ("LIKELY_NOT_EXPLOITABLE", safe))
                 if total}
    return {"dispositions": {"accuracy_by_expected_label": per_label}}


def test_the_gate_counts_a_language_only_when_both_directions_are_right():
    by_language = {"python": language(), "javascript": language(exploitable=(2, 3), safe=(1, 4)),
                   "java": language(safe=(0, 2)),         # every not-exploitable case mislabelled
                   "ruby": language(safe=(0, 0)),         # one direction only
                   "perl": {"dimensions": {}},            # no chain dispositions
                   "common": language()}                  # language-free never counts
    assert release_check.decisive_languages({"rollups": {"by_language": by_language}}) == ["javascript", "python"]
