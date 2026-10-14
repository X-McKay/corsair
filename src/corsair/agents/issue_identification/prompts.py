"""Identification instructions, skills and typed-input request rendering for both source modes."""

from pathlib import Path
from pydantic_ai.agent.spec import AgentSpec
from ..issue_analysis.contracts import IssueAnalysisInput
from ..source.repository import RepositoryLimits, SourceTree, list_tree
from .contracts import RepositoryIssueInput
from .skills import (
    REPOSITORY_SKILL_ID, REPOSITORY_SKILL_SHA256, REPOSITORY_SKILL_TEXT, SKILL_ID, SKILL_SHA256, SKILL_TEXT,
)

# PROMPT_VERSION covers everything the model sees; CONFIG_VERSION in agent.py covers budgets,
# instrumentation and composition. Each source mode is versioned separately (SPEC-0038).
_SPEC = AgentSpec.from_file(Path(__file__).with_name('agent.yaml'))
PROMPT_VERSION = _SPEC.metadata['prompt_version']
INSTRUCTIONS = _SPEC.instructions

_REPOSITORY_SPEC = AgentSpec.from_file(Path(__file__).with_name('repository-agent.yaml'))
REPOSITORY_PROMPT_VERSION = _REPOSITORY_SPEC.metadata['prompt_version']
REPOSITORY_INSTRUCTIONS = _REPOSITORY_SPEC.instructions


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
