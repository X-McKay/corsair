"""SPEC-0072: run activity events from the chain and its agents, and their terminal view."""
import asyncio
import io

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry, models
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from rich.console import Console

from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.adapters.terminal import TerminalDisplay
from corsair.composition.direct import StageModels, run_direct
from corsair.composition.progress import (Activity, GateDecided, ModelFailed, ModelTurn, Retry, RevisionEnded,
                                          RevisionStarted, RunEnded, StageEnded, StageStarted, ToolCalled,
                                          ToolReturned, Usage, clean, observing, preview)
from evals.fixture_e2e.case import (fixture_case, reviewed_runners, scripted_assessment, scripted_authoring,
                                    scripted_identification, scripted_planning)


@pytest.fixture(autouse=True)
def no_real_requests():
    with models.override_allow_model_requests(False):
        yield


@pytest.fixture
def store(tmp_path):
    (tmp_path / "artifacts").mkdir(mode=0o700)
    with LocalArtifacts(tmp_path / "artifacts", max_bytes=1024 * 1024) as artifacts:
        yield artifacts


def chain(store, root, observe=None, **overrides):
    (root / "work").mkdir(parents=True)
    models_ = dict(identification=scripted_identification(), planning=scripted_planning(),
                   authoring=scripted_authoring(), assessment=scripted_assessment()) | overrides
    return asyncio.run(run_direct(fixture_case(), StageModels(**models_), reviewed_runners(store, root / "work"),
                                  observe=observe))


def boundaries(events):
    return [(type(e).__name__, e.stopped_at if isinstance(e, RunEnded) else getattr(e, "stage", getattr(e, "revision", None)),
             getattr(e, "outcome", None))
            for e in events if isinstance(e, (StageStarted, StageEnded, RevisionStarted, RevisionEnded, GateDecided,
                                              RunEnded))]


def test_a_complete_run_reports_each_stage_revision_and_the_gate_in_order(store, tmp_path):
    events = []
    run = chain(store, tmp_path, events.append)
    assert run.stopped_at is None
    agent = lambda stage: [("StageStarted", stage, None), ("StageEnded", stage, "ready")]
    assert boundaries(events) == [
        *agent("identification"), *agent("planning"), *agent("authoring"),
        ("StageStarted", "execution", None),
        ("RevisionStarted", "baseline", None), ("RevisionEnded", "baseline", "ran"),
        ("RevisionStarted", "candidate", None), ("RevisionEnded", "candidate", "ran"),
        ("StageEnded", "execution", "ready"), ("GateDecided", None, None),
        *agent("assessment"), ("RunEnded", None, None)]
    assert events[-1].verdict and events[-1].stopped_at is None
    # Each agent stage's end carries what it spent against its own caps, as its attempt records them.
    ended = {e.stage: e.usage for e in events if isinstance(e, StageEnded) and e.usage}
    for attempt in run.attempts:
        spent = ended[attempt.stage]
        assert (spent.requests, spent.tool_calls, spent.tool_calls_limit) == (
            attempt.usage.requests, attempt.usage.tool_calls, attempt.limits.tool_calls_limit)
    turns = [e for e in events if isinstance(e, ModelTurn) and e.stage == "authoring"]
    assert [e.turn for e in turns] == list(range(1, len(turns) + 1)) and turns[-1].answered
    tools = [(e.tool, e.outcome) for e in events if isinstance(e, ToolReturned) and e.stage == "authoring"]
    assert ("write_test_file", "ok") in tools and ("run_tests", "ok") in tools
    baseline = next(e for e in events if isinstance(e, RevisionEnded) and e.revision == "baseline")
    assert "test_security_rejects_outside_read failed" in baseline.detail


def test_a_stopped_run_reports_the_stage_and_reason_and_starts_nothing_after(store, tmp_path):
    async def abstain(messages, info):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "status": "missing_information", "scope": "component", "target": None,
            "reason": "The configured documents directory is not in the saved source"})])
    events = []
    run = chain(store, tmp_path, events.append, identification=FunctionModel(abstain))
    assert run.stopped_at == "identification"
    assert boundaries(events) == [("StageStarted", "identification", None), ("StageEnded", "identification", "stopped"),
                                  ("RunEnded", "identification", None)]
    assert events[-1].reason == clean(run.reason, 2048) and "missing_information" in events[-1].reason


def test_observing_reaches_runs_started_inside_it_and_no_others(store, tmp_path):
    seen = []
    with observing(seen.append):
        chain(store, tmp_path / "inside")
    count = len(seen)
    assert count and isinstance(seen[-1], RunEnded)
    chain(store, tmp_path / "outside")
    assert len(seen) == count


class Answer(BaseModel):
    value: int


def test_agent_hooks_report_turns_tool_outcomes_and_retries_without_changing_the_run():
    def script():
        calls = iter([
            [ToolCallPart("lookup", {"key": "a", "api_token": "s3cret"})],  # tool asks for a retry
            [ToolCallPart("lookup", {"key": 7})],                            # arguments refused
            [ToolCallPart("lookup", {"key": "b"})],                          # ok
            "output:not-a-number",                                           # output refused
            "output:3"])

        def respond(messages, info):
            step = next(calls)
            if isinstance(step, str):
                return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"value": step.split(":")[1]})])
            return ModelResponse(parts=step)
        return FunctionModel(respond)

    def build():
        agent = Agent(script(), output_type=Answer, retries=3)
        tries = []

        @agent.tool_plain
        def lookup(key: str, api_token: str = "") -> str:
            tries.append(key)
            if len(tries) == 1:
                raise ModelRetry("not yet")
            return "found"
        return agent

    events = []
    watched = asyncio.run(build().run("go", capabilities=[Activity("planning", events.append)]))
    plain = asyncio.run(build().run("go"))
    assert watched.output == plain.output == Answer(value=3)
    assert [type(m) for m in watched.all_messages()] == [type(m) for m in plain.all_messages()]

    assert [(e.turn, e.tools, e.answered) for e in events if isinstance(e, ModelTurn)] == [
        (1, ("lookup",), False), (2, ("lookup",), False), (3, ("lookup",), False), (4, (), True), (5, (), True)]
    assert [(e.tool, e.outcome) for e in events if isinstance(e, ToolReturned)] == [("lookup", "retry"),
                                                                                   ("lookup", "ok")]
    assert [(e.target, e.name) for e in events if isinstance(e, Retry)] == [("tool arguments", "lookup"),
                                                                            ("output", "")]
    first = next(e for e in events if isinstance(e, ToolCalled))
    assert first.arguments == 'key="a", api_token=[masked]'


def test_a_tool_error_and_a_model_error_are_reported_and_still_raised():
    async def broken(messages, info):
        raise ConnectionError("provider unreachable")
    events = []
    with pytest.raises(ConnectionError):
        asyncio.run(Agent(FunctionModel(broken)).run("go", capabilities=[Activity("identification", events.append)]))
    assert events == [ModelFailed("identification", "ConnectionError", "provider unreachable")]

    agent = Agent(FunctionModel(lambda messages, info: ModelResponse(parts=[ToolCallPart("explode", {})])))

    @agent.tool_plain
    def explode() -> str:
        raise ValueError("boom")
    events = []
    with pytest.raises(ValueError):
        asyncio.run(agent.run("go", capabilities=[Activity("authoring", events.append)]))
    returned = [e for e in events if isinstance(e, ToolReturned)]
    assert [(e.tool, e.outcome, e.detail) for e in returned] == [("explode", "error", "ValueError: boom")]


def test_display_text_cannot_carry_terminal_controls_or_credentials():
    hostile = "read \x1b]0;owned\x07 \x1b[2J file\r\nnext\x00 Bearer abcdefghijklmnop ghp_ABCDEFGHIJKLMNOP1234"
    shown = clean(hostile)
    assert "\x1b" not in shown and "\x07" not in shown and "\r" not in shown and "\x00" not in shown
    assert "abcdefghijklmnop" not in shown and "ABCDEFGHIJKLMNOP1234" not in shown
    assert clean("x" * 500, 20) == "x" * 19 + "…"
    assert preview({"path": "a.py", "password": "p", "Authorization": "Basic zz", "lines": [1, 2]}) == (
        'path="a.py", password=[masked], Authorization=[masked], lines=<list>')
    assert preview('{"path": "a.py"}') == 'path="a.py"'


EVENTS = [StageStarted("identification"),
          ModelTurn("identification", 1, ("read_source",), False, Usage(1, 0, 1500, 2.0, 20, 16, 128000, 300)),
          ToolCalled("identification", "read_source", 'path="a.py"'),
          ToolReturned("identification", "read_source", "retry", "path is not in the saved source", 0.1),
          Retry("identification", "output", "", "1 error(s); line: must be positive"),
          StageEnded("identification", "stopped", "identification produced no output: UnexpectedModelBehavior",
                     Usage(3, 1, 4200, 9.0, 20, 16, 128000, 300)),
          RunEnded("identification", "identification produced no output", None)]


def test_off_a_terminal_the_display_prints_plain_unwrapped_lines():
    out = io.StringIO()
    with TerminalDisplay("case x", file=out) as display:
        for event in EVENTS:
            display(event)
    lines = out.getvalue().splitlines()
    assert "\x1b" not in out.getvalue() and len(lines) == 7
    assert lines[1].endswith(" identification started")
    assert 'identification tool read_source(path="a.py") retry 0.1s: path is not in the saved source' in lines[3]
    assert lines[-2].endswith("| turns 3 · tools 1/16 · tokens 4.2k/128k · 9s/300s")
    assert lines[-1].endswith("result stopped at identification — identification produced no output")


def test_on_a_terminal_the_display_colors_its_lines_and_clears_its_status_line():
    out = io.StringIO()
    console = Console(file=out, force_terminal=True, color_system="truecolor", width=200)
    with TerminalDisplay("case x", console=console) as display:
        assert display.status is not None
        for event in EVENTS:
            display(event)
    assert display.status is None
    text = out.getvalue()
    assert "\x1b[" in text and "stopped at identification" in text and "read_source" in text
