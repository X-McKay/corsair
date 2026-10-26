"""Auditor agent construction with only its packaged procedural skill loader."""

from __future__ import annotations

from collections.abc import Sequence

from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm
from google.adk.tools.skill_toolset import SkillToolset
from google.genai import types

from corsair.agents.resources import load_agent_spec, prompt_text

from .contracts import AuditResult


def build_auditor(model: str | BaseLlm, tools: Sequence[SkillToolset]) -> LlmAgent:
    """Build a fresh, outcome-blind structured semantic reviewer."""

    selected_tools = list(tools)
    spec = load_agent_spec("auditor")
    if spec.source_tools:
        raise ValueError("auditor metadata must not grant source tools")
    if len(selected_tools) != 1 or not isinstance(selected_tools[0], SkillToolset):
        raise ValueError("auditor must receive exactly one native SkillToolset")
    loader = selected_tools[0]
    if [skill.name for skill in loader.skills] != spec.runtime_skills:
        raise ValueError("auditor SkillToolset skills do not match approved metadata")
    if loader.tool_filter != spec.loader_tools:
        raise ValueError("auditor SkillToolset tools do not match approved metadata")
    if spec.instruction_resource != "corsair.agents.auditor.instructions:system.md":
        raise ValueError("auditor instruction resource metadata is not canonical")
    if spec.schema_ref != "corsair.contracts.AuditResult":
        raise ValueError("auditor schema metadata is not canonical")

    return LlmAgent(
        name=spec.name,
        description="Outcome-blind semantic review of a producer submission.",
        model=model,
        instruction=prompt_text("auditor")
        + "\n\n"
        + "\n\n".join(
            f"## Runtime procedure: {skill.name}\n{skill.instructions}" for skill in loader.skills
        ),
        tools=selected_tools,
        include_contents="none",
        output_schema=AuditResult,
        generate_content_config=types.GenerateContentConfig(response_mime_type="application/json"),
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )
