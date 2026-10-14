"""Identification instructions, skills and typed-input request rendering for both source modes."""

from ..spec import load_agent_spec
from ..issue_analysis.contracts import IssueAnalysisInput
from ..source.repository import RepositoryLimits, SourceTree, list_tree
from .contracts import RepositoryIssueInput
from .skills import (
    REPOSITORY_SKILL_ID, REPOSITORY_SKILL_SHA256, REPOSITORY_SKILL_TEXT, SKILL_ID, SKILL_SHA256, SKILL_TEXT,
)

# PROMPT_VERSION covers everything the model sees; CONFIG_VERSION in agent.py covers budgets,
# instrumentation and composition. Each source mode is versioned separately (SPEC-0038).
PROMPT_VERSION = load_agent_spec('identification').metadata.prompt_version
INSTRUCTIONS = load_agent_spec('identification').spec.instructions

REPOSITORY_PROMPT_VERSION = load_agent_spec('repository_identification').metadata.prompt_version
REPOSITORY_INSTRUCTIONS = load_agent_spec('repository_identification').spec.instructions


def identification_prompt(inputs: IssueAnalysisInput) -> str:
    return inputs.model_dump_json(exclude={"source_files", "fixture_id"}) + "\nSaved source inventory: " + ", ".join(
        f"{source.path} (saved-file inclusive lines 1..{len(source.content.splitlines())})" for source in inputs.source_files
    )


def repository_identification_prompt(inputs: RepositoryIssueInput, tree: SourceTree, limits: RepositoryLimits) -> str:
    root = list_tree(tree, limits)
    entries = ", ".join(f"{entry.path}{'/' if entry.kind == 'directory' else ''} ({entry.files} files)"
                        for entry in root.entries) + (" (truncated)" if root.truncated else "")
    return (inputs.model_dump_json(exclude={"case_id"})
            + f"\nSaved repository: {len(tree.sizes)} files at the commit above. Root entries: {entries}"
            + f"\nTool result budget for this run: {limits.run_bytes} bytes.")


__all__ = ["INSTRUCTIONS", "PROMPT_VERSION", "REPOSITORY_INSTRUCTIONS", "REPOSITORY_PROMPT_VERSION",
           "REPOSITORY_SKILL_ID", "REPOSITORY_SKILL_SHA256", "REPOSITORY_SKILL_TEXT", "SKILL_ID", "SKILL_SHA256",
           "SKILL_TEXT", "identification_prompt", "repository_identification_prompt"]
