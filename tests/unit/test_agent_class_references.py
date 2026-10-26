"""Per-class packaged references: packaging, trusted-code selection, and injection.

These cover the two delivery paths for the same packaged notes: the trusted-code
path (a pure selector plus a bounded packet hook) and the on-demand loader path
(exercised in test_agents_runtime). None of this calls a live model.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from corsair.adapters.inference.adk import _auditor_prompt, _producer_prompt
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.agents.auditor.contracts import AuditInput
from corsair.agents.resources import (
    _MAX_REFERENCE_BYTES,
    load_runtime_skills,
    runtime_skill_digest,
    select_reference,
)
from corsair.contracts import Finding
from corsair.contracts.agents import Submission
from tests.unit.test_agents import _producer_input, _submit_args

_EXPECTED_REFERENCES = {
    "code-execution.md",
    "command-injection.md",
    "error-exposure.md",
    "mass-assignment.md",
    "path-confinement.md",
    "ssrf-allowlist.md",
    # Selected by recipe kind rather than by finding class.
    "command-sentinel.md",
}


def _finding(title: str, description: str = "finding body") -> Finding:
    return Finding(title=title, description=description, file="app.py")


def test_both_roles_package_the_same_class_and_kind_references_as_text():
    for role in ("producer", "auditor"):
        skill = load_runtime_skills(role)[0]
        assert set(skill.resources.references) == _EXPECTED_REFERENCES
        for name, content in skill.resources.references.items():
            assert isinstance(content, str) and content
            assert len(content.encode()) <= _MAX_REFERENCE_BYTES
            assert name.endswith(".md")


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Path traversal in read_doc", "references/path-confinement.md"),
        ("Document path validation", "references/path-confinement.md"),
        ("OS command injection in count_lines", "references/command-injection.md"),
        ("Code injection in compute_setting", "references/code-execution.md"),
        ("Deserialization of untrusted data in load_profile", "references/code-execution.md"),
        ("Information exposure through an error message", "references/error-exposure.md"),
        ("Mass assignment in update_profile", "references/mass-assignment.md"),
        ("Server-side request forgery in fetch_preview", "references/ssrf-allowlist.md"),
    ],
)
def test_trusted_code_selects_one_reference_by_finding_class(title: str, expected: str):
    for role in ("producer", "auditor"):
        selected = select_reference(role, _finding(title), "python.secret_disclosure/1")
        assert selected is not None
        relative, text = selected
        assert relative == expected
        assert text and len(text.encode()) <= _MAX_REFERENCE_BYTES


def test_selection_is_none_for_an_unclear_class_or_unknown_recipe_kind():
    unclear = _finding("Unusual behavior", "no class keyword appears here at all")
    assert select_reference("producer", unclear, "python.secret_disclosure/1") is None
    # A recipe kind without packaged references selects nothing even on a clear class.
    assert select_reference("producer", _finding("Path traversal"), "other.kind/9") is None


@pytest.mark.parametrize("title", ["OS command injection in count_lines", "Unusual behavior"])
def test_command_sentinel_kind_selects_its_own_note_whatever_the_class(title: str):
    # The property is fixed by the recipe kind, so the class words do not matter.
    for role in ("producer", "auditor"):
        selected = select_reference(role, _finding(title), "python.command_sentinel/1")
        assert selected is not None
        relative, text = selected
        assert relative == "references/command-sentinel.md"
        assert "sentinel" in text


def test_producer_packet_appends_the_selected_reference_only_for_a_clear_class(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    base = _producer_input(store)

    traversal = base.model_copy(
        update={
            "prepared": base.prepared.model_copy(
                update={"finding": _finding("Path traversal in read_doc")}
            )
        }
    )
    packet = _producer_prompt(traversal)
    assert "## Class reference: references/path-confinement.md" in packet
    assert "Path confinement payload pair" in packet

    # The default fixture finding names no class, so nothing is appended.
    assert "## Class reference" not in _producer_prompt(base)


def test_auditor_packet_appends_the_selected_reference_for_a_clear_class(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    prepared = _producer_input(store).prepared
    audit_input = AuditInput(
        finding=_finding("Server-side request forgery in fetch_preview"),
        recipe=prepared.recipe,
        source_excerpt=prepared.source_excerpt,
        submission=Submission(**_submit_args()),
        max_output_tokens=512,
    )
    packet = _auditor_prompt(audit_input)
    assert "## Class reference: references/ssrf-allowlist.md" in packet
    assert "Reviewing an SSRF" in packet


def test_references_are_not_preloaded_into_either_role_instruction():
    for role in ("producer", "auditor"):
        skill = load_runtime_skills(role)[0]
        for content in skill.resources.references.values():
            assert isinstance(content, str)
            assert content not in skill.instructions


def test_runtime_digest_covers_reference_bytes():
    producer = load_runtime_skills("producer")[0]
    # A reference's text contributes to the role's runtime identity digest.
    sample = producer.resources.references["path-confinement.md"]
    assert isinstance(sample, str) and "Path confinement" in sample
    assert len(runtime_skill_digest("producer")) == 64
    assert runtime_skill_digest("producer") != runtime_skill_digest("auditor")


def test_submit_args_helper_is_importable():
    # Guard the shared helper import used by the auditor packet assertions.
    assert "plan" in _submit_args()
