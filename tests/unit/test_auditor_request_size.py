"""Size and shape pins for the auditor's rendered single request.

Renders every frozen auditor row through ``corsair.evaluation.preview`` (the renderer
behind ``corsair agent preview``), which drives the production run_auditor path with a
capturing model; no provider is called. Sizes are UTF-8 bytes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from corsair.contracts import AuditInput
from corsair.evaluation import preview
from corsair.evaluation.datasets import load_frozen_fixture
from corsair.settings import ModelSettings

ROOT = Path(__file__).resolve().parents[2]
EVALS_ROOT = ROOT / "evals"
AUDITOR_DATASETS = [
    ROOT / "evals/datasets/auditor-dev.json",
    ROOT / "evals/datasets/auditor-expanded.json",
    ROOT / "evals/datasets/auditor-rubric.json",
]

# With its SkillToolset the auditor's system instruction plus tool declarations
# rendered 7,683 bytes on the LiteLLM route (6,806 natively): ADK's generic skill
# guidance, the set_model_response note and three tool declarations.
MAX_SYSTEM_AND_TOOLS_BYTES = 3_800


def _dataset_fixtures(datasets: list[Path]) -> list[tuple[str, bytes]]:
    """Each distinct frozen auditor input once, digest-verified; the oracle stays unused."""
    fixtures: list[tuple[str, bytes]] = []
    for dataset_path in datasets:
        for entry in json.loads(dataset_path.read_bytes())["entries"]:
            if entry["case_id"] not in {case_id for case_id, _ in fixtures}:
                _input_path, content, _oracle = load_frozen_fixture(EVALS_ROOT, entry)
                fixtures.append((entry["case_id"], content))
    return fixtures


@pytest.mark.asyncio
@pytest.mark.parametrize("structured_tools", [False, True])
async def test_every_frozen_audit_is_one_tool_free_schema_request(structured_tools: bool):
    fixtures = _dataset_fixtures(AUDITOR_DATASETS)

    assert [case_id for case_id, _ in fixtures] == [f"audit{index:02d}" for index in range(1, 12)]
    for _case_id, content in fixtures:
        requests, output = await preview.capture_auditor(
            AuditInput.model_validate_json(content),
            ModelSettings(),
            structured_tools=structured_tools,
        )
        usage = output.usage
        assert (len(requests), usage.llm_calls, usage.tool_calls) == (1, 1, 0)
        assert preview.declared_tool_names(requests[0]) == []
        assert output.review is not None
        sections = preview.request_sections("auditor", requests[0])
        assert sections["tool_declarations"] == ""
        assert sections["response_schema"] != ""
        assert sections["conversation"] == ""
        system_and_tools = (
            sections["corsair_instruction"]
            + sections["adk_instruction"]
            + sections["tool_declarations"]
        )
        assert len(system_and_tools.encode()) <= MAX_SYSTEM_AND_TOOLS_BYTES


@pytest.mark.asyncio
async def test_rendered_audit_instruction_carries_no_adk_tool_guidance():
    _case_id, content = _dataset_fixtures(AUDITOR_DATASETS[:1])[0]

    requests, output = await preview.capture_auditor(
        AuditInput.model_validate_json(content), ModelSettings(), structured_tools=False
    )
    sections = preview.request_sections("auditor", requests[0])

    assert output.feedback is None and output.review is not None
    assert "## Runtime procedure: semantic-review\n" in sections["corsair_instruction"]
    for absent in ("set_model_response", "load_skill", "<available_skills>", "MUST use"):
        assert absent not in sections["adk_instruction"]
