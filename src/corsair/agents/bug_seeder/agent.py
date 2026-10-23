"""Proposal-only inverse-mode bug seeding."""

from __future__ import annotations

from pydantic_ai import Agent, UsageLimits
from pydantic_ai.models import Model

from corsair.agents.bug_seeder.types import SeededBug
from corsair.agents.resources import instruction, validate_agent_spec
from corsair.domain.case import SafePath


def instructions() -> str:
    """Lazily load the proposal-only seed instruction."""
    return instruction(__package__)


def build_bug_seeder(model: Model) -> Agent[None, SeededBug]:
    """Build a spec-validated tool-free proposal agent."""
    validate_agent_spec(__package__, tool_names=())
    return Agent(model, output_type=SeededBug, retries=0, name="bug-seeder", instructions=instructions())


async def propose_seed(model: Model, target_file: str, source: str, vulnerability_class: str) -> SeededBug:
    """Request one minimal patch confined to the named source file; baseline/replay testing is separate."""
    from pydantic import TypeAdapter

    target_file = TypeAdapter(SafePath).validate_python(target_file)
    if (
        not source
        or len(source.encode()) > 64_000
        or not vulnerability_class
        or len(vulnerability_class) > 128
    ):
        raise ValueError("seed requires a nonempty source of at most 64 KB and a bounded vulnerability class")
    result = await build_bug_seeder(model).run(
        f"Target: {target_file}\nClass: {vulnerability_class}\nSource:\n{source}",
        usage_limits=UsageLimits(request_limit=1),
    )
    proposal = result.output
    if proposal.target_file != target_file:
        raise ValueError("seed proposal changed the target file")
    headers = [line for line in proposal.git_diff.splitlines() if line.startswith(("--- ", "+++ "))]
    if headers != [f"--- a/{target_file}", f"+++ b/{target_file}"]:
        raise ValueError(
            "seed diff must modify exactly the named file; additions, removals and extra files are forbidden"
        )
    if not any(line.startswith("@@ ") for line in proposal.git_diff.splitlines()):
        raise ValueError("seed diff must contain a unified diff hunk")
    return proposal
