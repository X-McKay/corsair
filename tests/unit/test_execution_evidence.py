"""V3 recording rejects invented outcomes and plan/source receipt substitution."""

import pytest

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts.execution import (
    ExecutionResult,
    ExecutionRound,
    PlanAudit,
    ProcessObservation,
)
from corsair.contracts.execution import (
    TestPlan as Plan,
)
from corsair.settings import Settings
from corsair.steps.execution import ExecutionActivities


@pytest.mark.asyncio
async def test_record_refuses_success_without_process_evidence(tmp_path):
    store = ArtifactStore(tmp_path)
    activities = ExecutionActivities(Settings(artifact_root=str(tmp_path)), store)
    result = ExecutionResult(run_id="forged", case_id="case").model_copy(
        update={"outcome": "SUCCEEDED"}
    )
    with pytest.raises(ValueError):
        await activities.record(result)


@pytest.mark.asyncio
async def test_record_refuses_observation_without_admitted_request(tmp_path):
    store = ArtifactStore(tmp_path)
    observation = ProcessObservation(
        operation_id="op",
        source_digest="1" * 64,
        image_id="sha256:" + "2" * 64,
        plan_digest="3" * 64,
        error="SETUP_FAILED",
        outcome="ERROR",
        cleanup_confirmed=True,
    )
    ref = store.put_json(observation)
    store.commit("execution.op", ref)
    observation = observation.model_copy(update={"artifact": ref})
    plan = Plan(
        hypothesis="Not the observed plan",
        revision=1,
        commands=[{"argv": ["true"]}],
        locations=[{"path": "reader.py"}],
    )
    result = ExecutionResult(
        run_id="forged",
        case_id="case",
        rounds=[
            ExecutionRound(plan=plan, audit=PlanAudit(decision="accepted"), observation=observation)
        ],
    )
    with pytest.raises(ValueError):
        await ExecutionActivities(Settings(artifact_root=str(tmp_path)), store).record(result)
