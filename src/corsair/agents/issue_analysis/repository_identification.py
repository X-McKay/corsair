"""Moved to `corsair.agents.issue_identification` (SPEC-0052); old imports keep working."""

from ..issue_identification.agent import REPOSITORY_CONFIG_VERSION as CONFIG_VERSION
from ..issue_identification.agent import create_repository_identification_agent
from ..issue_identification.contracts import RepositoryIdentity, RepositoryIssueInput
from ..issue_identification.dependencies import RepositoryDependencies
from ..issue_identification.prompts import REPOSITORY_INSTRUCTIONS as INSTRUCTIONS
from ..issue_identification.prompts import REPOSITORY_PROMPT_VERSION as PROMPT_VERSION
from ..issue_identification.prompts import repository_identification_prompt
from ..issue_identification.skills import REPOSITORY_SKILL_ID as SKILL_ID
from ..issue_identification.skills import REPOSITORY_SKILL_SHA256 as SKILL_SHA256
from ..issue_identification.skills import REPOSITORY_SKILL_TEXT as SKILL_TEXT
from ..issue_identification.tools import REPOSITORY_TOOLSET_ID as TOOLSET_ID

__all__ = ["CONFIG_VERSION", "INSTRUCTIONS", "PROMPT_VERSION", "SKILL_ID", "SKILL_SHA256", "SKILL_TEXT", "TOOLSET_ID",
           "RepositoryDependencies", "RepositoryIdentity", "RepositoryIssueInput",
           "create_repository_identification_agent", "repository_identification_prompt"]
