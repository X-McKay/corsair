"""Native ADK intake factory with canonical structured output."""

from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm
from google.adk.tools.skill_toolset import SkillToolset
from google.genai import types

from corsair.agents.resources import load_agent_spec, prompt_text
from corsair.contracts.intake_agent import ImageInventory
from corsair.ports.intake import InspectionReader

from .contracts import IntakeProposal
from .toolsets import build_intake_toolset


def build_intake(
    model: str | BaseLlm,
    reader: InspectionReader,
    inventory: ImageInventory,
    byte_limit: int = 32768,
) -> LlmAgent:
    spec = load_agent_spec("intake")
    if (
        spec.schema_ref != "corsair.contracts.IntakeProposal"
        or spec.instruction_resource != "corsair.agents.intake.instructions:system.md"
    ):
        raise ValueError("noncanonical intake resource metadata")
    tools = build_intake_toolset(reader, inventory, byte_limit)
    loader = tools[-1]
    if not isinstance(loader, SkillToolset):
        raise ValueError("intake must use its private native SkillToolset")
    return LlmAgent(
        name="intake",
        model=model,
        instruction=prompt_text("intake")
        + "\n\n"
        + "\n\n".join(
            f"## Runtime procedure: {skill.name}\n{skill.instructions}" for skill in loader.skills
        ),
        tools=tools,
        output_schema=IntakeProposal,
        generate_content_config=types.GenerateContentConfig(response_mime_type="application/json"),
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )
