"""Builder: propose a setup Recipe and a passing baseline test in a disposable workspace (stage 4, ``BuildAgent``).

One native agent from ``agent.yaml``. The stage passes the workspace (a native PydanticAI ``Workspace``) to the run;
the agent explores it with ``run`` and the read-only Harness file tools. Investigate runs first (amendment A1), so
the prompt names the planned target and the files the plan cites: the Builder prepares that component, not the
whole repository. It sees no finding text and no hypothesis. The Recipe is only a proposal: trusted replay
(``build.replay``) runs it again in a fresh container and decides whether it holds.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic_ai import Agent, RunContext
from pydantic_ai.agent.spec import AgentSpec
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits
from pydantic_ai.workspaces import LocalWorkspaceBackend, Workspace
from pydantic_ai_harness import Skills

from corsair.v2.contracts import AgentUsage, Case, ProbePlan, Recipe, Runtime

from ..common.budget import tool_budget
from ..common.prompted_output import prompted_output
from ..common.usage import run_recorded
from .tools import builder_tools, file_tools
from .validation import check_recipe

PACKAGE = Path(__file__).parent
SPEC = AgentSpec.from_file(PACKAGE / "agent.yaml")
SKILL_ID = "recipe-search"
LIMITS = UsageLimits(request_limit=40, tool_calls_limit=30)
"""Operator budget: domain tools are withdrawn at the tool cap so the agent still answers."""


@dataclass(frozen=True)
class BuilderDeps:
    framework: str


def create_agent(model: Model, *, durability: TemporalDurability | None = None,
                 output_retries: int = 1) -> Agent[BuilderDeps, Recipe]:
    if not isinstance(model, Model):
        raise TypeError("an explicit native Model instance is required")
    agent = Agent.from_spec(
        SPEC, model=model, deps_type=BuilderDeps, output_type=Recipe,
        retries={"tools": 2, "output": output_retries}, toolsets=[builder_tools()],
        capabilities=[
            file_tools(),
            Skills("skills", include=[SKILL_ID], workspace=LocalWorkspaceBackend(PACKAGE)),
            tool_budget(),
            prompted_output(),
            *([durability] if durability is not None else []),
        ])

    @agent.output_validator
    def ran_here(ctx: RunContext[BuilderDeps], recipe: Recipe) -> Recipe:
        return check_recipe(recipe, ctx.messages)

    return agent


def render_prompt(runtime: Runtime, plan: ProbePlan) -> str:
    cited = sorted({citation.path for brief in (plan.control, plan.exploit) if brief is not None
                    for citation in brief.citations} | {citation.path for citation in plan.citations})
    component = (f"Component under test: {plan.target}. Files the plan cites: {', '.join(cited)}."
                 if plan.target else "Component under test: not yet known; prepare the project as a whole.")
    test_dir = runtime.test_dir.strip("/") or "the repository's own test directory"
    return "\n\n".join((
        component,
        f"Test framework: {runtime.framework}. Probe tests will later be added under: {test_dir}.",
        "How trusted code will run one test (argv template; {file} and {name} are filled in): "
        + " ".join(runtime.run_template),
    ))


async def build_agent(case: Case, runtime: Runtime, plan: ProbePlan, model: Model, *, workspace: Workspace,
                      feedback: str | None = None) -> tuple[Recipe | None, AgentUsage]:
    """Stage entry. ``workspace`` already holds the revision tree in its working directory.

    ``feedback`` is set only for the one extra episode (A2): why trusted replay of the previous recipe failed.
    """
    agent = create_agent(model)
    prompt = render_prompt(runtime, plan)
    if feedback:
        prompt += ("\n\nA previous recipe failed when trusted code replayed it in a fresh container. "
                   "Replay output (untrusted data):\n" + feedback[-6_000:])
    return await run_recorded(agent, "builder", prompt, model=model,
                              deps=BuilderDeps(framework=runtime.framework), usage_limits=LIMITS,
                              workspace=workspace)
