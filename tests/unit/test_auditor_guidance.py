"""Native auditor guidance delivery regressions using the standard ADK test model."""

from __future__ import annotations

import json

import pytest

from corsair.adapters.inference.adk import run_auditor
from corsair.agents.resources import load_runtime_skills
from corsair.contracts import (
    AuditDecision,
    AuditInput,
    AuditResult,
    Finding,
    PlanRevision,
    PythonRecipe,
    Submission,
)
from corsair.settings import ModelSettings
from tests.unit.adk import ScriptedLlm, text_response


def _audit_input() -> AuditInput:
    return AuditInput(
        finding=Finding(
            title="Controlled file read",
            description="Assess the configured caller-controlled file name only.",
            file="reader.py",
            line=2,
        ),
        recipe=PythonRecipe(
            module_file="reader.py",
            function="read",
            payload_parameter="payload",
            fixed_kwargs={"base_root": "/fixtures/allowed"},
        ),
        source_excerpt=(
            "def read(payload, *, base_root):\n    return open(f'{base_root}/{payload}').read()\n"
        ),
        submission=Submission(
            hypothesis=(
                "The declared payload is used to build the path beneath the fixed base root "
                "without a containment check."
            ),
            plan=PlanRevision(
                revision=1,
                objective="Compare a public filename with a parent traversal.",
                next_steps=["Submit the declared positional payload pair."],
                reason="The declared payload parameter is caller controlled.",
            ),
            control_payload="hello.txt",
            exploit_payload="../private/secret.txt",
        ),
        max_output_tokens=512,
    )


def _accepted_response() -> str:
    return json.dumps(
        {
            "decision": "ACCEPT",
            "rule": "coherent-proposed-test",
            "reason": "The declared payload pair invokes the supplied production callable.",
        }
    )


def _first_user_message(model: ScriptedLlm) -> str:
    assert len(model.requests) == 1
    request = model.requests[0]
    assert len(request.contents) == 1
    content = request.contents[0]
    assert content.role == "user"
    assert len(content.parts) == 1
    text = content.parts[0].text
    assert text is not None
    return text


@pytest.mark.asyncio
async def test_auditor_first_request_preloads_ordered_semantic_guidance():
    model = ScriptedLlm(
        model="scripted-auditor-guidance", responses=[text_response(_accepted_response())]
    )

    output = await run_auditor(_audit_input(), ModelSettings(), model)

    assert output.feedback is None
    assert output.review is not None
    assert output.review.decision is AuditDecision.ACCEPT
    assert output.usage.skills_preloaded == ["semantic-review"]
    assert output.usage.skills_loaded == []
    assert output.usage.tool_calls == 0
    request = model.requests[0]
    assert request.config.response_schema is AuditResult
    instruction = str(request.config.system_instruction)
    sufficiency = instruction.index("First, use `INSUFFICIENT_CONTEXT`")
    contradiction = instruction.index("Second, when that supplied context")
    acceptance = instruction.index("Otherwise, use `ACCEPT`")
    assert sufficiency < contradiction < acceptance
    assert "unavailable execution evidence, private fixture contents, coverage" in instruction
    assert "concretely contradicts a claimed mechanism or bypass" in instruction
    assert "honestly expects a visible guard to\nhold" in instruction
    procedure = load_runtime_skills("auditor")[0]
    assert f"## Runtime procedure: {procedure.name}\n{procedure.instructions}" in instruction


@pytest.mark.asyncio
async def test_auditor_first_request_has_only_the_outcome_blind_auditable_packet():
    model = ScriptedLlm(
        model="scripted-auditor-packet", responses=[text_response(_accepted_response())]
    )

    output = await run_auditor(_audit_input(), ModelSettings(), model)

    assert output.feedback is None
    request = model.requests[0]
    assert set(request.tools_dict) == {"load_skill", "load_skill_resource"}
    message = _first_user_message(model)
    prefix = "Review this outcome-blind packet only. Do not infer execution results or a final "
    assert message.startswith(prefix)
    packet = json.loads(message.split("\n", maxsplit=1)[1])
    assert set(packet) == {
        "finding",
        "recipe_public_configuration",
        "observer_fixture_location",
        "source_excerpt",
        "submission",
    }
    assert packet["observer_fixture_location"] == "/fixtures/private/secret.txt"
    assert packet["recipe_public_configuration"]["fixed_kwargs"] == {
        "base_root": "/fixtures/allowed"
    }
    assert "fixed_source" not in packet
    assert "outcome" not in json.dumps(packet)
