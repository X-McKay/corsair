"""Typed, proposal-only playbook modification output."""

from pydantic import Field

from corsair.domain.case import Frozen


class SkillPatchProposal(Frozen):
    # Legacy .md names remain the CLI proposal surface; callers map them to skills/<slug>/SKILL.md.
    skill_file: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}\.md$")
    rationale: str = Field(min_length=1, max_length=1_000)
    markdown_append_block: str = Field(min_length=1, max_length=2_000)
