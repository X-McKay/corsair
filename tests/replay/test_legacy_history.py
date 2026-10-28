"""Genuine base-revision history replay, without running its scripted activities."""

from pathlib import Path

import pytest
from temporalio.client import WorkflowHistory
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Replayer

from corsair.contracts import InvestigationResult
from corsair.workflows.investigation import InvestigationWorkflow

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]


@pytest.mark.parametrize("kind", ["positive", "held"])
async def test_pre_assessment_history_replays_with_unchanged_v1_completion(kind: str):
    path = Path(__file__).parent / "histories" / f"pre-assessment-{kind}.json"
    content = path.read_text()
    assert "assessment-outcomes-v1" not in content
    history = WorkflowHistory.from_json(f"legacy-assessment-{kind}", content)
    completed = next(
        event.workflow_execution_completed_event_attributes
        for event in history.events
        if event.HasField("workflow_execution_completed_event_attributes")
    )
    (result,) = await pydantic_data_converter.decode(
        completed.result.payloads, [InvestigationResult]
    )
    assert result.schema_version == "corsair.result/1"
    assert result.assessment_outcome is None
    assert "assessment_outcome" not in result.model_dump(mode="json")
    outcome = await Replayer(
        workflows=[InvestigationWorkflow], data_converter=pydantic_data_converter
    ).replay_workflow(history)
    assert outcome.replay_failure is None
