"""Moved to `corsair.agents.issue_identification` (SPEC-0052); old imports keep working."""

from ..issue_identification.agent import CONFIG_VERSION, create_issue_identification_agent
from ..issue_identification.dependencies import IdentificationDependencies
from ..issue_identification.prompts import INSTRUCTIONS, PROMPT_VERSION, identification_prompt
from ..issue_identification.skills import SKILL_ID, SKILL_SHA256, SKILL_TEXT
from ..issue_identification.validation import _symbol_occurs, finalize_draft

__all__ = ["CONFIG_VERSION", "INSTRUCTIONS", "PROMPT_VERSION", "SKILL_ID", "SKILL_SHA256", "SKILL_TEXT",
           "IdentificationDependencies", "_symbol_occurs", "create_issue_identification_agent", "finalize_draft",
           "identification_prompt"]
