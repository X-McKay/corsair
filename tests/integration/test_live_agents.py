"""Optional real-provider smoke coverage.

This module is inert unless an operator supplies a worker-only settings file
through ``CORSAIR_LIVE_CONFIG``. No endpoint, credentials, or model IDs are
committed here.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from corsair.adapters.inference.adk import run_auditor
from corsair.contracts import AuditInput, Finding, PythonRecipe, Submission
from corsair.settings import load_settings


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_auditor_completes_one_real_outcome_blind_review():
    config = os.environ.get("CORSAIR_LIVE_CONFIG")
    if not config:
        pytest.skip("set CORSAIR_LIVE_CONFIG to enable a real-provider smoke")

    path = Path(config)
    assert path.is_file(), "CORSAIR_LIVE_CONFIG must name an operator-provided settings file"
    settings = load_settings(path)
    audit_input = AuditInput(
        finding=Finding(
            title="Return value may disclose input",
            description="The callable appears to return its untrusted payload argument.",
            file="target.py",
            line=2,
        ),
        recipe=PythonRecipe(
            module_file="target.py",
            function="render",
            payload_parameter="payload",
            fixed_kwargs={"prefix": "safe:"},
        ),
        source_excerpt="1: def render(payload, *, prefix):\n2:     return prefix + payload\n",
        submission=Submission(
            control_payload="hello",
            exploit_payload="untrusted-value",
            hypothesis="The return expression includes the supplied payload.",
            plan={
                "revision": 1,
                "parent_revision": None,
                "objective": "exercise the configured callable declaratively",
                "next_steps": ["submit the payload pair"],
                "reason": "the admitted source returns payload",
            },
        ),
        max_output_tokens=512,
    )

    output = await run_auditor(audit_input, settings)

    assert output.feedback is None
    assert output.review is not None
    assert output.usage.llm_calls == 1
    assert output.usage.tool_calls == 0
