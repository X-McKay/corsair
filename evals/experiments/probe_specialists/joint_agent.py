"""Matched joint baseline: exact specialist skill union, same source-read admission."""
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.capabilities import Capability, Instrumentation
from pydantic_ai.models.instrumented import InstrumentationSettings
from corsair.agents.budget import tool_budget
from corsair.agents.prompted_output import prompted_output
from corsair.agents.source.contracts import SourceRead
from corsair.agents.test_authoring.tools._history import _successful
from evals.experiments.split_authoring.dependencies import DraftingDependencies
from evals.experiments.split_authoring.contracts import DraftOutput, Drafted, Blocked
from evals.experiments.split_authoring.tools import drafting_tools
from evals.experiments.split_authoring.validation import finalize_draft
from .prompts import CONTROL_INSTRUCTIONS, EXPLOIT_INSTRUCTIONS, COMMON_INSTRUCTIONS, COMMON_SKILL_ID, COMMON_SKILL_TEXT, CONTROL_SKILL_ID, CONTROL_SKILL_TEXT, EXPLOIT_SKILL_ID, EXPLOIT_SKILL_TEXT

async def finalize_joint(ctx: RunContext[DraftingDependencies], draft: DraftOutput) -> Drafted | Blocked:
    result = await finalize_draft(ctx, draft)
    if result.status == 'drafted':
        reads = []
        for _, returned in _successful(ctx, 'read_source'):
            try:
                read = SourceRead.model_validate(returned.content)
            except ValueError:
                continue
            if read.path in {s.path for s in ctx.deps.inputs.source_files}:
                expected = ctx.deps.read_source(read.path, read.start_line, read.end_line)
                if tuple(line.text for line in read.lines) != tuple(expected.quote.splitlines()):
                    raise ModelRetry('Source read differs from immutable joint input')
                reads.append(read)
        if not all(any(r.path == c.path and r.start_line <= c.start_line and c.end_line <= r.end_line for r in reads) for c in ctx.deps.inputs.property_plan.citations):
            raise ModelRetry('Read source covering every supplied property anchor before returning drafted')
    return result

def create_joint_agent(model, *, output_retries=4):
    framing = '\nAuthor exactly the control and exploit in their two owned files. Each specialist section applies to its corresponding probe; fulfill both roles. Neither section limits the joint assignment to one total file.'
    return Agent(model, name='joint_probe_author', deps_type=DraftingDependencies,
        output_type=finalize_joint, instructions=COMMON_INSTRUCTIONS + "\n" + CONTROL_INSTRUCTIONS + "\n" + EXPLOIT_INSTRUCTIONS + framing,
        retries={'tools': 0, 'output': output_retries},
        capabilities=[Capability(id=COMMON_SKILL_ID, instructions=COMMON_SKILL_TEXT, toolsets=[drafting_tools()]),
            Capability(id=CONTROL_SKILL_ID, instructions=CONTROL_SKILL_TEXT),
            Capability(id=EXPLOIT_SKILL_ID, instructions=EXPLOIT_SKILL_TEXT), tool_budget(), prompted_output(), Instrumentation(settings=InstrumentationSettings(include_content=False,version=5))])
