"""Issue identification: locate the implementation relevant to a reported concern (SPEC-0024, SPEC-0038)."""

from .agent import (
    MANIFEST_IDENTITY, SPEC_SHA256, REPOSITORY_MANIFEST_IDENTITY, REPOSITORY_SPEC_SHA256,
    CONFIG_VERSION, PROMPT_VERSION, REPOSITORY_CONFIG_VERSION, REPOSITORY_PROMPT_VERSION, REPOSITORY_TOOLSET_SHA256,
    TOOLSET_SHA256, create_issue_identification_agent, create_repository_identification_agent, identification_prompt,
    repository_identification_prompt,
)
from .contracts import IssueIdentification, IssueIdentificationDraft, RepositoryIdentity, RepositoryIssueInput
from .dependencies import FixtureDependencies, RepositoryDependencies

__all__ = ["CONFIG_VERSION", "PROMPT_VERSION", "REPOSITORY_CONFIG_VERSION", "REPOSITORY_PROMPT_VERSION",
           "REPOSITORY_TOOLSET_SHA256", "TOOLSET_SHA256", "FixtureDependencies", "IssueIdentification",
           "IssueIdentificationDraft", "RepositoryDependencies", "RepositoryIdentity", "RepositoryIssueInput",
           "create_issue_identification_agent", "create_repository_identification_agent", "identification_prompt",
           "repository_identification_prompt"]
