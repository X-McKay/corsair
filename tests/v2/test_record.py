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
             "diagnose-control", "diagnose-exploit", "review.1", "execute-control-vulnerable",
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
    assert summary["review"] == {"rounds": 1, "authors": {
        role: {"first_review_valid": True, "revisions_used": 0, "final_valid": True, "recovered": False}
        for role in ("control", "exploit")}}
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


# --- Run-record schema corsair-v2-run/1 (RUN_RECORD.md) ----------------------------------------------------------


def _schema_run(tmp_path, **fakes_kwargs):
    from dataclasses import replace

    tmp_path.mkdir(parents=True, exist_ok=True)
    fakes = Fakes(**fakes_kwargs)
    stages = replace(fakes.stages(), inspect_image=lambda ref: f"sha256:{'9' * 64}" if ref == "image:1" else None)
    providers, matrix = tmp_path / "providers.json", tmp_path / "matrix.yaml"
    providers.write_text("{}\n")
    matrix.write_text("rows: []\n")
    record = RunRecorder.create(tmp_path / "runs", "run-s")
    asyncio.run(run_case(case(tmp_path), stages=stages, models=models(), matrix_path=matrix, record=record,
                         provider_config=providers))
    return tmp_path / "runs" / "run-s", providers, matrix


def test_run_json_records_what_produced_the_run(tmp_path):
    import hashlib

    run_dir, providers, matrix = _schema_run(tmp_path)
    run = _load(run_dir / "run.json")
    assert run["schema"] == "corsair-v2-run/1" and run["run_id"] == "run-s" and run["case_id"] == "case-1"
    assert run["mode"] == "direct" and run["hostname"]
    assert run["started_at"].endswith("Z") and run["finished_at"] >= run["started_at"]
    assert run["git_commit"] is None or len(run["git_commit"]) == 40
    assert run["provider_config_sha256"] == hashlib.sha256(providers.read_bytes()).hexdigest()
    assert run["matrix_sha256"] == hashlib.sha256(matrix.read_bytes()).hexdigest()
    assert (run["runtime_row"], run["runtime_image"], run["runtime_image_id"]) == ("row", "image:1",
                                                                                   f"sha256:{'9' * 64}")
    assert run["revision"] == {"tree_sha256": "0" * 64, "commit": None} and run["fixed_revision"] is None
    # The environment image was not inspectable here, so its id is unknown, never invented.
    assert run["environments"]["vulnerable"] == {"image": "env:1", "image_id": None, "tree_sha256": "0" * 64,
                                                 "recipe_sha256": "0" * 64, "runtime_row": "row"}


def test_usage_rows_carry_parameters_versions_and_retries(tmp_path):
    run_dir, _, _ = _schema_run(tmp_path)
    rows = {row["step"]: row for row in _load(run_dir / "usage.json")}
    reviewer = rows["review.1"]
    assert reviewer["prompt_version"] == "reviewer-v2-3" and reviewer["config_version"] is None
    assert len(reviewer["spec_sha256"]) == 64
    assert rows["investigate"]["config_version"] == "v2-investigator-config-1"
    # TestModel has no settings and fake stages pass no limits: unknown, never zero.
    for key in ("provider_host", "temperature", "max_tokens", "thinking", "request_limit", "tool_calls_limit",
                "max_output_retries"):
        assert reviewer[key] is None
    # The investigator fake ran a native agent, so its history was captured and its retries are a known count.
    assert rows["investigate"]["retries"] == 0 and reviewer["retries"] is None


def test_summary_has_outcome_agents_models_and_totals(tmp_path):
    run_dir, _, _ = _schema_run(tmp_path)
    summary = _load(run_dir / "summary.json")
    assert summary["schema"] == "corsair-v2-run/1" and summary["mode"] == "direct"
    outcome = summary["outcome"]
    assert (outcome["label"], outcome["rule_id"], outcome["terminal_reason"], outcome["fix_reason"]) == (
        "LIKELY_EXPLOITABLE", "R4", "ok", None)
    assert set(outcome["probes"]["vulnerable"]) == {"control", "exploit"}
    probe = outcome["probes"]["vulnerable"]["exploit"]
    assert probe["outcome"] == "passed" and probe["facts"]["exit_code"] == 0 and probe["tree_sha256"] is None
    assert summary["models"] == ["test"]
    reviewer = summary["agents"]["reviewer"]
    assert (reviewer["calls"], reviewer["requests"], reviewer["input_tokens"], reviewer["output_tokens"]) == (
        1, 1, 10, 5)
    assert reviewer["statuses"] == {"ok": 1} and reviewer["prompt_versions"] == ["reviewer-v2-3"]
    assert reviewer["retries"] is None and summary["agents"]["investigator"]["retries"] == 0
    assert summary["totals"]["retries"] is None  # one unknown makes the total unknown


def test_parameters_come_from_native_settings_and_limits_and_retries_from_messages():
    from openai import AsyncOpenAI
    from pydantic_ai import Agent, ModelRetry
    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.usage import UsageLimits

    from corsair.v2.agents.common.usage import model_parameters, run_recorded
    from corsair.v2.models import ModelProfile, build_model

    profile = ModelProfile(base_url="https://llm.example/v1", model_name="m",
                           temperature=0.2, max_tokens=4096, thinking_token_budget=1024)
    native = build_model(profile, openai_client=AsyncOpenAI(base_url=profile.base_url, api_key="unused"))
    assert model_parameters(native) == {"model": "m", "provider_host": "llm.example", "temperature": 0.2,
                                        "max_tokens": 4096, "thinking": "budget", "thinking_budget": 1024}
    off = build_model(profile.model_copy(update={"thinking": "disabled", "thinking_token_budget": None}),
                      openai_client=AsyncOpenAI(base_url=profile.base_url, api_key="unused"))
    assert model_parameters(off)["thinking"] == "disabled"

    answers = iter(["first", "second"])
    model = FunctionModel(lambda messages, info: ModelResponse(parts=[TextPart(next(answers))]),
                          model_name="scripted", settings={"temperature": 0.0, "max_tokens": 64})
    agent = Agent(model, output_type=str, retries={"tools": 1, "output": 2})

    @agent.output_validator
    def once(text: str) -> str:
        if text == "first":
            raise ModelRetry("try again")
        return text

    output, usage = asyncio.run(run_recorded(agent, "reviewer", "go", model=model,
                                             usage_limits=UsageLimits(request_limit=5, tool_calls_limit=3)))
    assert output == "second" and usage.retries == 1 and usage.requests == 2
    assert (usage.model, usage.temperature, usage.max_tokens, usage.thinking) == ("scripted", 0.0, 64,
                                                                                  "server_default")
    assert (usage.request_limit, usage.tool_calls_limit, usage.max_output_retries, usage.max_tool_retries) == (
        5, 3, 2, 1)
    assert usage.prompt_version == "reviewer-v2-3" and usage.provider_host is None


def test_compare_prints_one_row_per_run(tmp_path, capsys):
    from corsair.v2.cli import main

    first, _, _ = _schema_run(tmp_path / "a")
    second, _, _ = _schema_run(tmp_path / "b", plan=None)
    assert main(["runs", "compare", str(first), str(second)]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0].split()[:6] == ["run", "case", "mode", "label", "rule", "reason"]
    assert len(lines) == 3
    assert "LIKELY_EXPLOITABLE" in lines[1] and "R4" in lines[1] and "rev=reviewer-v2-3" in lines[1]
    assert "plan_unresolved" in lines[2] and "rev=" not in lines[2]
    assert lines[1].split()[7] == "75" and lines[2].split()[7] == "15"  # tokens
