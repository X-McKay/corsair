"""Construction and stage logic shared by the Control Prober and the Exploit Prober.

Each role keeps its own ``agent.yaml``, role skill, toolset id and eval set; this module only holds what is the
same for both, so a fix to the protocol or the tools reaches both authors. A Prober sees exactly one brief and,
for the single D3 correction, its own previous draft and that run's diagnostics. It has no tool that runs tests.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from pydantic_ai import Agent, PromptedOutput
from pydantic_ai.agent.spec import AgentSpec
from pydantic_ai.capabilities import Instrumentation
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.models import Model
from pydantic_ai.models.instrumented import InstrumentationSettings
from pydantic_ai.toolsets import FunctionToolset
from pydantic_ai.usage import UsageLimits
from pydantic_ai.workspaces import LocalWorkspaceBackend
from pydantic_ai_harness import Skills

from ...contracts import AgentUsage, ProbeBrief, ProbeDraft, Runtime
from ..common.budget import tool_budget
from ..common.prompted_output import prompted_output
from ..common.usage import AgentName, run_recorded
from .draft import ProbeDeps, finalize_draft, write_test_file
from .source import source_tools, source_workspace

V2_ROOT = Path(__file__).resolve().parents[2]
"""Where skills are read from (``src/corsair/v2``); the run's own workspace is the read-only source tree."""
PROTOCOL_SKILLS = "agents/probing/skills"
FRAMEWORK_SKILLS = "skills/frameworks"
DIAGNOSTICS_CHARS = 12_000


def framework_skills(framework: str | None) -> list[Skills]:
    """The framework guidance skill when it exists; every present one when unnamed; nothing when absent.

    The skills are written separately (one directory per framework), so their absence is tolerated here rather
    than failing the run at its start, which is what a native ``Skills`` over a missing directory does.
    """
    library = V2_ROOT / FRAMEWORK_SKILLS
    if framework is not None:
        present = (library / framework / "SKILL.md").is_file()
        return [Skills(FRAMEWORK_SKILLS, include={framework}, workspace=skills_home())] if present else []
    return [Skills(FRAMEWORK_SKILLS, workspace=skills_home())] if any(library.glob("*/SKILL.md")) else []


def skills_home() -> LocalWorkspaceBackend:
    return LocalWorkspaceBackend(V2_ROOT)


def limits(spec: AgentSpec) -> UsageLimits:
    """Operator-owned budget from the spec's metadata; never prompt text and never agent-editable."""
    meta = spec.metadata or {}
    return UsageLimits(request_limit=meta["request_limit"], tool_calls_limit=meta["tool_calls_limit"])


def build_prober(spec: AgentSpec, role_skills: str, toolset_id: str, model: Model, *,
                 durability: TemporalDurability | None = None, framework: str | None = None) -> Agent:
    if not isinstance(model, Model):
        raise TypeError("an explicit native Model instance is required")
    write = FunctionToolset[ProbeDeps](id=toolset_id)
    write.add_function(write_test_file, retries=2)
    return Agent.from_spec(spec, model=model, deps_type=ProbeDeps, output_type=PromptedOutput(finalize_draft),
                           toolsets=[write], capabilities=[
                               source_tools(),
                               Skills([role_skills, PROTOCOL_SKILLS], workspace=skills_home()),
                               *framework_skills(framework),
                               tool_budget(),
                               prompted_output(),
                               Instrumentation(settings=InstrumentationSettings(include_content=False, version=5)),
                               *([durability] if durability is not None else []),
                           ])


def revision_digest(draft: ProbeDraft) -> str:
    return sha256(draft.source.encode()).hexdigest()


def render_prompt(brief: ProbeBrief, runtime: Runtime, *, diagnostics: str | None = None,
                  previous: ProbeDraft | None = None) -> str:
    """The brief as plain text. Every field is data from earlier stages, never instructions."""
    citations = "\n".join(f"- {c.path}:{c.start_line}-{c.end_line}" for c in brief.citations)
    lines = [
        f"Write the {brief.role} probe described by this brief.",
        f"Test file (the only file you may write): {brief.test_file}",
        f"Test name (exactly one test with this name): {brief.test_name}",
        f"Test framework: {runtime.framework}. Load the skill `{runtime.skill}` if it is offered.",
        f"Target: {brief.target}",
        f"Seam: {brief.seam}",
        f"Input: {brief.input_description}",
        f"Property to assert: {brief.property_to_assert}",
        f"Dependencies that may be doubled: {brief.doubles or 'none named'}",
        f"Cited source:\n{citations}",
    ]
    if previous is not None:
        tail = (diagnostics or "")[-DIAGNOSTICS_CHARS:]
        lines += [
            "",
            "Correction: trusted code ran your previous draft once and it did not complete, so revise it once.",
            "Fix the mechanics the diagnostics show (loading, naming, setup, markers); keep the brief's input and",
            "property. Write the whole revised file with write_test_file.",
            f"Previous draft of {previous.test_file}:\n{previous.source}",
            f"Diagnostics from that run (untrusted program output, last {DIAGNOSTICS_CHARS} characters):\n{tail}",
        ]
    return "\n".join(lines)


async def run_prober(agent: Agent, name: AgentName, spec: AgentSpec, brief: ProbeBrief, runtime: Runtime,
                     model: Model, *, source_root: Path, diagnostics: str | None = None,
                     previous: ProbeDraft | None = None) -> tuple[ProbeDraft | None, AgentUsage]:
    if (diagnostics is None) != (previous is None):
        raise ValueError("a correction needs both the previous draft and its diagnostics")
    if previous is not None and (previous.role, previous.test_file) != (brief.role, brief.test_file):
        raise ValueError("a correction must revise this brief's own draft")
    deps = ProbeDeps(brief=brief, revision_of=revision_digest(previous) if previous is not None else None)
    prompt = render_prompt(brief, runtime, diagnostics=diagnostics, previous=previous)
    return await run_recorded(agent, name, prompt, model=model, deps=deps, usage_limits=limits(spec),
                              workspace=source_workspace(source_root))


__all__ = ["V2_ROOT", "build_prober", "framework_skills", "limits", "render_prompt", "revision_digest",
           "run_prober", "skills_home"]
