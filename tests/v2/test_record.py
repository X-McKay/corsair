"""The run recorder writes every stage, usage and the verdict, and keeps unknown usage unknown."""
import asyncio
import json

import pytest

from chain_fakes import Fakes, case, models, usage
from corsair.v2.chain import run_case
from corsair.v2.contracts import AgentUsage, Label, TerminalReason, Verdict
from corsair.v2.record import RunRecorder


def _load(path):
    return json.loads(path.read_text())


def test_run_directory_holds_every_stage_usage_messages_and_verdict(tmp_path):
    fakes = Fakes(grounding=True)
    record = RunRecorder.create(tmp_path / "runs", "run-1")
    asyncio.run(run_case(case(tmp_path), stages=fakes.stages(), models=models(), matrix_path=tmp_path / "m.yaml",
                         record=record))
    run = tmp_path / "runs" / "run-1"
    assert _load(run / "case.json")["case_id"] == "case-1"
    assert _load(run / "run.json")["mode"] == "direct"
    steps = ["ground", "select", "investigate", "build", "replay-build", "probe-control", "probe-exploit",
             "diagnose-control", "diagnose-exploit", "review-vulnerable", "execute-control-vulnerable",
             "execute-exploit-vulnerable", "decide"]
    assert [t["step"] for t in _load(run / "timings.json")] == steps
    for step in steps:
        stage = _load(run / "stages" / f"{step}.json")
        assert stage["step"] == step and stage["error"] is None and stage["wall_s"] is not None
        assert "input" in stage and "output" in stage
    assert _load(run / "stages" / "investigate.json")["output"]["status"] == "planned"
    agents = _load(run / "usage.json")
    assert [a["agent"] for a in agents] == ["grounding", "investigator", "builder", "control_prober",
                                            "exploit_prober", "reviewer"]
    assert all(a["wall_s"] is not None for a in agents)
    # The investigator fake ran a native agent, so its history is saved; the others ran none.
    messages = _load(run / "agents" / "investigate.messages.json")
    assert messages and messages[0]["kind"] == "request"
    assert not (run / "agents" / "build.messages.json").exists()
    assert _load(run / "grounding.json")["summary"] == "context ctx"
    assert _load(run / "verdict.json")["label"] == "LIKELY_EXPLOITABLE"
    summary = _load(run / "summary.json")
    assert (summary["label"], summary["rule_id"], summary["terminal_reason"]) == ("LIKELY_EXPLOITABLE", "R4", "ok")
    assert summary["totals"]["agent_calls"] == 6
    assert summary["totals"]["requests"] == 6 and summary["totals"]["tokens"] == 90
    assert summary["totals"]["tool_calls"] == 0 and summary["totals"]["wall_s"] is not None


def test_unknown_usage_stays_null_never_zero(tmp_path):
    unknown = AgentUsage(agent="reviewer")  # the stage reported nothing
    fakes = Fakes(usages={"reviewer": unknown, "builder": usage("builder", tool_calls=None)})
    record = RunRecorder.create(tmp_path, "run")
    asyncio.run(run_case(case(tmp_path), stages=fakes.stages(), models=models(), matrix_path=tmp_path,
                         record=record))
    rows = _load(tmp_path / "run" / "usage.json")
    reviewer = next(r for r in rows if r["agent"] == "reviewer")
    assert reviewer["requests"] is None and reviewer["input_tokens"] is None and reviewer["wall_s"] is not None
    totals = _load(tmp_path / "run" / "summary.json")["totals"]
    assert totals["requests"] is None and totals["tokens"] is None and totals["input_tokens"] is None
    assert totals["tool_calls"] is None
    assert totals["agent_calls"] == 5


def test_failed_agent_call_is_recorded_with_its_error(tmp_path):
    from pydantic_ai.exceptions import ModelHTTPError
    fakes = Fakes(raises={"investigate": ModelHTTPError(503, "m")})
    record = RunRecorder.create(tmp_path, "run")
    asyncio.run(run_case(case(tmp_path), stages=fakes.stages(), models=models(), matrix_path=tmp_path,
                         record=record))
    stage = _load(tmp_path / "run" / "stages" / "investigate.json")
    assert "ModelHTTPError" in stage["error"] and stage["output"] is None
    row = _load(tmp_path / "run" / "usage.json")[0]
    assert row["status"] == "provider_error" and row["requests"] is None
    summary = _load(tmp_path / "run" / "summary.json")
    assert summary["terminal_reason"] == "provider_error" and summary["totals"]["requests"] is None


def test_no_agent_calls_is_a_known_zero(tmp_path):
    record = RunRecorder.create(tmp_path, "run")
    record.begin(case(tmp_path), mode="direct")
    summary = record.finish(Verdict(case_id="case-1", label=Label.UNABLE_TO_RUN, rule_id="R0",
                                    terminal_reason=TerminalReason.NO_RUNTIME, finding="none", fix="not_applicable"))
    assert summary["totals"]["agent_calls"] == 0 and summary["totals"]["requests"] == 0


def test_default_root_is_under_the_working_directory_and_runs_never_overwrite(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    record = RunRecorder.create()
    assert record.run_dir.parent == tmp_path / ".runs" / "v2" / "runs"
    with pytest.raises(FileExistsError):
        RunRecorder.create(run_id=record.run_id)
    with pytest.raises(ValueError):
        record.stage("../escape", inputs={}, output=None, wall_s=None)
