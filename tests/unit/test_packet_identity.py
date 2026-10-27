"""Per-role packet digests: the packet builders' output enters the run manifest identity.

Each role ships one frozen probe request with the package. ``build_manifest`` renders it
through the live packet builders (and, for the producer, the live toolset's native ADK
declarations) and records the digest, so a change to section order, keys, excerpt rules
or class-reference selection changes the configuration identity of every later run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from corsair.adapters.inference import adk
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.agents.resources import packet_probe_text
from corsair.contracts import (
    AuditInput,
    InvestigationRequest,
    PreparedCase,
    ProducerInput,
    RunManifest,
)
from corsair.evaluation import preview
from corsair.settings import ModelSettings, Settings
from corsair.steps import manifest

ROOT = Path(__file__).resolve().parents[2]
KERNEL = ROOT / "tests/replay/kernel/case02.gym-tier1-20261027t012146-ade22e.c1.r0.json"


def _build(tmp_path: Path) -> RunManifest:
    request = InvestigationRequest.model_validate_json(
        (ROOT / "evals/fixtures/case01/request.json").read_bytes()
    )
    return manifest.build_manifest(
        request, Settings(artifact_root=str(tmp_path)), "sha256:" + "a" * 64
    )


def test_the_probe_renders_to_the_same_digest_every_time(tmp_path: Path):
    first, second = _build(tmp_path), _build(tmp_path)
    for role in ("producer", "auditor"):
        assert adk.probe_packet_digest(role) == adk.probe_packet_digest(role)
        assert len(adk.probe_packet_digest(role)) == 64
    assert first.producer_packet_digest == second.producer_packet_digest
    assert first.auditor_packet_digest == second.auditor_packet_digest
    assert first.producer_packet_digest == adk.probe_packet_digest("producer")
    assert first.auditor_packet_digest == adk.probe_packet_digest("auditor")
    assert first.producer_packet_digest != first.auditor_packet_digest
    # The digest is over the packet and tool declarations, not the instruction file.
    assert first.producer_packet_digest != first.producer_prompt_digest


def test_the_probe_covers_the_builders_branches_and_carries_no_volatile_value():
    producer = dict(adk.probe_packet_parts("producer"))
    auditor = dict(adk.probe_packet_parts("auditor"))
    assert list(producer) == ["tool.read_file", "tool.list_files", "packet"]
    assert list(auditor) == ["packet"]
    for packet in (producer["packet"], auditor["packet"]):
        # Class-reference selection and the derived-line note are both exercised.
        assert "## Class reference: references/path-confinement.md" in packet
        assert "target_line_provenance" in packet
        assert str(ROOT) not in packet
    # A round-2 producer packet carries the previous submission and its feedback.
    assert '"previous_feedback":{"gate":"audit_reject"' in producer["packet"]
    assert "## Submission\n" in auditor["packet"]
    for role in ("producer", "auditor"):
        text = packet_probe_text(role)
        assert str(ROOT) not in text
        assert "artifact_root" not in text


@pytest.mark.parametrize(
    ("builder", "changed", "kept"),
    [
        ("_producer_prompt", "producer_packet_digest", "auditor_packet_digest"),
        ("_auditor_prompt", "auditor_packet_digest", "producer_packet_digest"),
    ],
)
def test_a_changed_builder_output_changes_only_that_roles_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, builder: str, changed: str, kept: str
):
    before = _build(tmp_path)
    original = getattr(adk, builder)
    monkeypatch.setattr(adk, builder, lambda value: original(value).replace("## ", "### ", 1))
    after = _build(tmp_path)
    assert getattr(after, changed) != getattr(before, changed)
    assert getattr(after, kept) == getattr(before, kept)
    assert after.producer_prompt_digest == before.producer_prompt_digest
    assert after.auditor_prompt_digest == before.auditor_prompt_digest
    assert after.config_digest == before.config_digest


def test_a_changed_producer_tool_declaration_changes_the_producer_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    before = _build(tmp_path)
    original = adk.build_producer_toolset

    def renamed(producer_input, sources):
        tools = original(producer_input, sources)
        tools[0].__doc__ = "A reworded tool description."
        return tools

    monkeypatch.setattr(adk, "build_producer_toolset", renamed)
    after = _build(tmp_path)
    assert after.producer_packet_digest != before.producer_packet_digest
    assert after.auditor_packet_digest == before.auditor_packet_digest


@pytest.mark.asyncio
async def test_the_probe_digest_is_the_tool_and_packet_parts_agent_preview_captures(
    tmp_path: Path,
):
    """The same parts ``corsair agent preview`` splits a captured request into.

    The preview's ``request_sha256`` also covers the instruction parts and the response
    schema, so it differs from the packet digest; the tool and packet parts agree.
    """
    producer_input = ProducerInput.model_validate_json(packet_probe_text("producer"))
    requests, _output = await preview.capture_producer(
        producer_input,
        Settings(artifact_root=str(tmp_path)),
        ArtifactStore(tmp_path),
        structured_tools=True,
    )
    audit_input = AuditInput.model_validate_json(packet_probe_text("auditor"))
    audits, _review = await preview.capture_auditor(
        audit_input, ModelSettings(), structured_tools=True
    )
    for role, request in (("producer", requests[0]), ("auditor", audits[0])):
        parts = preview.request_parts(role, request)
        captured = [
            (part["name"], part["text"]) for part in parts if part["kind"] in ("tool", "packet")
        ]
        assert captured == adk.probe_packet_parts(role)
        assert adk.packet_parts_digest(captured) == adk.probe_packet_digest(role)
        whole = preview.build_preview(role, request, inputs={}, route={}, episode={})
        assert whole["request_sha256"] != adk.probe_packet_digest(role)


def test_a_manifest_stored_before_the_packet_digests_still_decodes():
    stored = json.loads(KERNEL.read_bytes())["prepared"]
    assert "producer_packet_digest" not in stored["manifest"]
    prepared = PreparedCase.model_validate(stored)
    assert prepared.manifest.producer_packet_digest is None
    assert prepared.manifest.auditor_packet_digest is None
    assert prepared.manifest.producer_prompt_digest == stored["manifest"]["producer_prompt_digest"]
