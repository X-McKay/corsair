import asyncio

from pydantic_ai import Agent
from pydantic_ai.messages import ToolReturnPart

from corsair.v2.agents.common.repetition import ALLOWED, read_loop_guard

from tests.v2.agent_scripts import Script


def test_identical_read_calls_past_the_allowance_are_not_run_again():
    reads = []

    def read_file(path: str) -> str:
        reads.append(path)
        return f"contents of {path}"

    script = Script([("read_file", {"path": "app.py"})] * 4 + [("read_file", {"path": "other.py"}), "done"])
    agent = Agent(script.model, tools=[read_file], capabilities=[read_loop_guard()])
    asyncio.run(agent.run("go"))
    assert reads == ["app.py"] * ALLOWED + ["other.py"]
    returns = [part.content for message in script.seen[-1] for part in message.parts
               if isinstance(part, ToolReturnPart)]
    assert returns[ALLOWED].startswith("You already made this exact read_file call")


def test_tools_outside_the_read_set_are_never_guarded():
    runs = []

    def run(argv: list[str]) -> str:
        runs.append(argv)
        return "ok"

    script = Script([("run", {"argv": ["make"]})] * 4 + ["done"])
    asyncio.run(Agent(script.model, tools=[run], capabilities=[read_loop_guard()]).run("go"))
    assert len(runs) == 4


def test_tools_are_withdrawn_before_either_cap_so_the_agent_can_answer():
    from pydantic_ai.usage import RunUsage, UsageLimits
    from corsair.v2.agents.common.budget import HEADROOM, within_tool_budget

    class Ctx:
        def __init__(self, tool_calls, requests):
            self.usage = RunUsage(tool_calls=tool_calls, requests=requests)
            self.usage_limits = UsageLimits(request_limit=40, tool_calls_limit=30)

    tools = ["t"]
    assert asyncio.run(within_tool_budget(Ctx(30 - HEADROOM - 1, 5), tools)) == tools
    assert asyncio.run(within_tool_budget(Ctx(30 - HEADROOM, 5), tools)) == []
    assert asyncio.run(within_tool_budget(Ctx(5, 40 - HEADROOM), tools)) == []
