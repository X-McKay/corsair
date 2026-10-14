"""Committed v2 baselines: what qualifies, what the file keeps, and comparison falling back to it."""
import json

import pytest

from evals import run as eval_run


def _run(results, agent, run_id, *, language=None, dirty=False, rollups=True, mode="live", attempts=1):
    run_dir = results / agent / run_id
    run_dir.mkdir(parents=True)
    summary = {"schema": "corsair-eval-summary/v1", "agent": agent, "set": "development", "language": language,
               "mode": mode, "run": run_id, "identity": {"git_commit": "abc", "git_dirty": dirty},
               "attempts": [{"case": "python/a"}],
               "rollups": {"all": {"clean_attempts": attempts, "attempts": attempts, "dimensions": {}}} if rollups else None}
    (run_dir / "summary.json").write_text(json.dumps(summary))
    (run_dir / "policy.json").write_text(json.dumps({"status": "not_set"}))
    return run_dir


@pytest.fixture
def target(tmp_path, monkeypatch):
    path = tmp_path / "agent-evals" / "baselines" / "development-live.json"
    monkeypatch.setattr(eval_run, "committed_baseline", lambda agent, set_name, mode: path)
    return path


def test_a_clean_whole_set_run_is_committed_without_attempt_rows(tmp_path, target):
    results = tmp_path / "results"
    _run(results, "builder", "20261014T120000Z-development-live")
    eval_run.commit_baseline("builder", "20261014T120000Z-development-live", results)
    record = json.loads(target.read_text())
    assert "attempts" not in record and record["rollups"]["all"]["attempts"] == 1
    assert record["policy_status"] == "not_set" and record["run"] == "20261014T120000Z-development-live"
    pointer = json.loads((results / "builder" / "baseline-development-live.json").read_text())
    assert pointer["run"] == "20261014T120000Z-development-live"


@pytest.mark.parametrize("kwargs", [{"language": "perl"}, {"dirty": True}, {"dirty": None}, {"rollups": False},
                                    {"mode": "scripted"}, {"attempts": 0}])
def test_narrowed_dirty_or_unreported_runs_are_not_baselines(tmp_path, target, kwargs):
    results = tmp_path / "results"
    _run(results, "builder", "20261014T120000Z-development-live", **kwargs)
    with pytest.raises(SystemExit):
        eval_run.commit_baseline("builder", "20261014T120000Z-development-live", results)
    assert not target.exists()


def test_comparison_falls_back_to_the_committed_baseline(tmp_path, target):
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"run": "20261014T120000Z-development-live", "rollups": {}, "identity": {}}))
    agent_dir = tmp_path / "results" / "builder"
    agent_dir.mkdir(parents=True)
    run_id, reference = eval_run._v2_reference(agent_dir, "development", "live", "20261015T000000Z-development-live")
    assert run_id == "20261014T120000Z-development-live" and reference["reference_kind"] == "committed baseline"


def test_a_pruned_promoted_run_falls_back_to_the_committed_baseline(tmp_path, target):
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"run": "20261014T120000Z-development-live", "rollups": {}, "identity": {}}))
    agent_dir = tmp_path / "results" / "builder"
    agent_dir.mkdir(parents=True)
    (agent_dir / "baseline-development-live.json").write_text(json.dumps({"run": "20261013T000000Z-development-live"}))
    run_id, reference = eval_run._v2_reference(agent_dir, "development", "live", "20261015T000000Z-development-live")
    assert run_id == "20261014T120000Z-development-live" and reference["reference_kind"] == "committed baseline"
