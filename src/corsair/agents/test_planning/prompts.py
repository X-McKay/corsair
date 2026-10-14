"""Planning instructions, skill and typed-input request rendering; no labels, discovery or external calls."""
from ..spec import load_agent_spec


from .contracts import TestPlanningInput
from .skills import SKILL_ID, SKILL_SHA256, SKILL_TEXT

# PROMPT_VERSION covers everything the model sees (instructions, skill, rendered user
# prompt, tool and output schema text); CONFIG_VERSION in agent.py covers budgets,
# instrumentation and provider composition.
_SPEC = load_agent_spec('planning')
PROMPT_VERSION = _SPEC.metadata.prompt_version
INSTRUCTIONS = _SPEC.spec.instructions

__all__ = ["INSTRUCTIONS", "PROMPT_VERSION", "SKILL_ID", "SKILL_SHA256", "SKILL_TEXT", "planning_prompt"]


def planning_prompt(inputs: TestPlanningInput) -> str:
    """Identification without its quotation (source evidence is re-derived from reads), environment and inventory only."""
    inventory = ", ".join(
        f"{source.path} (saved-file inclusive lines 1..{len(source.content.splitlines())})" for source in inputs.source_files
    ) or "(empty)"
    return inputs.model_dump_json(exclude={"source_files": True, "identification": {"target": {"source": {"quote"}}}}) + (
        "\nSaved source inventory (the only readable paths): " + inventory
        + "\nApproved test paths (files the authored tests will create; not readable): "
        + ", ".join(inputs.environment.approved_test_paths))
