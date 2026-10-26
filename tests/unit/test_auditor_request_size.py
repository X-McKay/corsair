"""Size and shape pins for the auditor's rendered single request.

Renders every frozen auditor row through scripts/measure_auditor_request.py, which
drives the production run_auditor path with a capturing model; no provider is called.
Sizes are UTF-8 bytes.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
MEASURE_SCRIPT = ROOT / "scripts/measure_auditor_request.py"
AUDITOR_DATASETS = [
    ROOT / "evals/datasets/auditor-dev.json",
    ROOT / "evals/datasets/auditor-expanded.json",
]

# With its SkillToolset the auditor's system instruction plus tool declarations
# rendered 7,683 bytes on the LiteLLM route (6,806 natively): ADK's generic skill
# guidance, the set_model_response note and three tool declarations.
MAX_SYSTEM_AND_TOOLS_BYTES = 3_800


def _measure_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("measure_auditor_request", MEASURE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
@pytest.mark.parametrize("structured_tools", [False, True])
async def test_every_frozen_audit_is_one_tool_free_schema_request(structured_tools: bool):
    measure = _measure_module()

    rows = await measure.measure(AUDITOR_DATASETS, structured_tools=structured_tools)

    assert [row["case_id"] for row in rows] == ["audit01", "audit02", "audit03", "audit04"]
    for row in rows:
        assert (row["requests"], row["llm_calls"], row["tool_calls"]) == (1, 1, 0)
        assert row["declared_tools"] == []
        assert row["review_parsed"] is True
        sections = row["sections"]
        assert sections["tool_declarations"]["bytes"] == 0
        assert sections["response_schema"]["bytes"] > 0
        assert sections["conversation"]["bytes"] == 0
        assert row["system_and_tools"]["bytes"] <= MAX_SYSTEM_AND_TOOLS_BYTES


@pytest.mark.asyncio
async def test_rendered_audit_instruction_carries_no_adk_tool_guidance():
    measure = _measure_module()
    _case_id, content = measure.dataset_fixtures(AUDITOR_DATASETS[:1])[0]

    requests, output = await measure.render_requests(content, structured_tools=False)
    sections = measure.request_sections(requests[0])

    assert output.feedback is None and output.review is not None
    assert "## Runtime procedure: semantic-review\n" in sections["corsair_instruction"]
    for absent in ("set_model_response", "load_skill", "<available_skills>", "MUST use"):
        assert absent not in sections["adk_instruction"]
