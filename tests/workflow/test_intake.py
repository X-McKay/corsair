"""Real Temporal command/replay boundary with explicit activity substitutes."""

from datetime import timedelta

import pytest
from temporalio import activity
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ApplicationError
from temporalio.worker import Replayer, Worker

from corsair.contracts import Source
from corsair.contracts.intake import (
    IntakeRequest,
    IntakeResult,
    IntakeStart,
    JsonIssueInput,
    PreparedIntake,
)
from corsair.workflows.intake import IntakeWorkflow
from tests.workflow.temporal import temporal_id

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio(loop_scope="module")]


class DeniedActivities:
    @activity.defn(name="corsair.intake.prepare")
    async def prepare(self, _start: IntakeStart) -> PreparedIntake:
        raise ApplicationError("source denied", type="SOURCE_DENIED", non_retryable=True)

    @activity.defn(name="corsair.intake.record")
    async def record(self, result: IntakeResult) -> IntakeResult:
        return result


async def test_intake_source_failure_is_recorded_and_replayable(temporal_server):
    activities = DeniedActivities()
    queue = temporal_id("intake")
    start = IntakeStart(
        run_id=temporal_id("intake-run"),
        request=IntakeRequest(
            input=JsonIssueInput(payload={"title": "issue"}), source=Source(path="denied")
        ),
    )
    async with Worker(
        temporal_server.client,
        task_queue=queue,
        workflows=[IntakeWorkflow],
        activities=[activities.prepare, activities.record],
    ):
        handle = await temporal_server.client.start_workflow(
            IntakeWorkflow.run,
            start,
            id=start.run_id,
            task_queue=queue,
            execution_timeout=timedelta(seconds=60),
        )
        result = await handle.result()
        assert result.decision.status == "error"
        assert result.decision.classification is None
        assert result.decision.error_code == "SOURCE_DENIED"
        history = await handle.fetch_history()
    await Replayer(
        workflows=[IntakeWorkflow], data_converter=pydantic_data_converter
    ).replay_workflow(history)


async def test_prepare_heartbeats_survive_slow_healthy_adapters(temporal_server):
    import asyncio

    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.contracts import digest
    from corsair.contracts.intake import ImageInventory, IntakeDecision
    from corsair.settings import Settings
    from corsair.steps.intake import IntakeActivities

    class SlowActivities(IntakeActivities):
        async def _prepare(self, start):
            await asyncio.sleep(16)
            reference = self.store.put_json({"fixture": "heartbeat-only"})
            return PreparedIntake(
                run_id=start.run_id,
                request=start.request,
                source=reference,
                input_artifact=reference,
                payload={},
                inventory=ImageInventory(),
                config_digest=digest({}),
            )

        @activity.defn(name="corsair.intake.analyze")
        async def analyze(self, prepared: PreparedIntake) -> IntakeResult:
            return IntakeResult(
                run_id=prepared.run_id,
                decision=IntakeDecision(
                    status="needs_input", reason_codes=["INSUFFICIENT_ISSUE_INFORMATION"]
                ),
            )

    from tempfile import TemporaryDirectory

    with TemporaryDirectory(prefix="intake-heartbeat-") as directory:
        activities = SlowActivities(Settings(artifact_root=directory), ArtifactStore(directory))
        queue = temporal_id("heartbeat")
        start = IntakeStart(
            run_id=temporal_id("heartbeat-run"),
            request=IntakeRequest(input=JsonIssueInput(payload={}), source=Source(path="admitted")),
        )
        async with Worker(
            temporal_server.client,
            task_queue=queue,
            workflows=[IntakeWorkflow],
            activities=activities.registered(),
        ):
            result = await temporal_server.client.execute_workflow(
                IntakeWorkflow.run,
                start,
                id=start.run_id,
                task_queue=queue,
                execution_timeout=timedelta(seconds=60),
            )
        assert result.decision.status == "needs_input"
