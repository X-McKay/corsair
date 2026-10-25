"""Auditor agent construction."""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.genai import types

from corsair.contracts import AuditResult
from corsair.runtime.models import AgentModel, load_agent_spec, prompt_text


def build_auditor(model: AgentModel) -> LlmAgent:
    """Build a fresh, tool-free, structured-output semantic reviewer."""

    spec = load_agent_spec("auditor")
    if spec.tools:
        raise ValueError("auditor metadata must not grant tools")
    if spec.instruction_resource != "corsair.agents.auditor.instructions:system.md":
        raise ValueError("auditor instruction resource metadata is not canonical")
    if spec.schema_ref != "corsair.contracts.AuditResult":
        raise ValueError("auditor schema metadata is not canonical")

    return LlmAgent(
        name=spec.name,
        description="Outcome-blind semantic review of a producer submission.",
        model=model,
        instruction=prompt_text("auditor"),
        tools=[],
        include_contents="none",
        output_schema=AuditResult,
        generate_content_config=types.GenerateContentConfig(response_mime_type="application/json"),
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )
