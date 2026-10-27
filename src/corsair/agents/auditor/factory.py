"""Auditor agent construction: one tool-free, schema-only structured review."""

from __future__ import annotations

from collections.abc import Sequence

from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm
from google.adk.skills import Skill
from google.genai import types

from corsair.agents.resources import load_agent_spec, load_runtime_skills, prompt_text

from .contracts import AuditResult


def auditor_instruction(skills: Sequence[Skill]) -> str:
    """Compose the auditor prompt with each admitted procedure preloaded after it."""

    return (
        prompt_text("auditor")
        + "\n\n"
        + "\n\n".join(
            f"## Runtime procedure: {skill.name}\n{skill.instructions}" for skill in skills
        )
    )


def build_auditor(
    model: str | BaseLlm, *, decoding: types.GenerateContentConfig | None = None
) -> LlmAgent:
    """Build a fresh, outcome-blind structured semantic reviewer with no tools.

    The admitted procedure is parsed by native ADK and preloaded into the
    instruction, so the agent needs no loader. With no tools, ADK sends the
    ``AuditResult`` response schema itself on every route instead of adding a
    ``set_model_response`` tool, and one JSON-mode request completes the review.
    ``decoding`` carries only the configured sampling parameters; JSON mode is added to it.
    """

    spec = load_agent_spec("auditor")
    if spec.tools or spec.source_tools or spec.loader_tools:
        raise ValueError("auditor metadata must not grant any tool")
    skills = load_runtime_skills("auditor")
    if [skill.name for skill in skills] != spec.runtime_skills:
        raise ValueError("auditor preloaded skills do not match approved metadata")
    if spec.instruction_resource != "corsair.agents.auditor.instructions:system.md":
        raise ValueError("auditor instruction resource metadata is not canonical")
    if spec.schema_ref != "corsair.contracts.AuditResult":
        raise ValueError("auditor schema metadata is not canonical")

    return LlmAgent(
        name=spec.name,
        description="Outcome-blind semantic review of a producer submission.",
        model=model,
        instruction=auditor_instruction(skills),
        tools=[],
        include_contents="none",
        output_schema=AuditResult,
        generate_content_config=(decoding or types.GenerateContentConfig()).model_copy(
            update={"response_mime_type": "application/json"}
        ),
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )
