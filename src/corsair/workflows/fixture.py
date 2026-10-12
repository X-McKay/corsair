"""One native parent/child composition, with retry ownership per fixture operation."""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

with workflow.unsafe.imports_passed_through():
    from .fixture_activities import complete_fixture, prepare_fixture
    from .fixture_contracts import FixtureRequest, FixtureResult


@workflow.defn
class FixtureStage:
    def __init__(self) -> None:
        self._released = False
        self._waiting = False

    @workflow.signal
    def release(self) -> None:
        self._released = True

    @workflow.query
    def waiting(self) -> bool:
        return self._waiting

    @workflow.run
    async def run(self, request: FixtureRequest) -> FixtureResult:
        try:
            prepared = await workflow.execute_activity(
                prepare_fixture, request,
                start_to_close_timeout=timedelta(seconds=10),
                schedule_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(initial_interval=timedelta(milliseconds=100),
                                         maximum_attempts=3),
            )
        except ActivityError as error:
            cause = error.cause
            if not isinstance(cause, ApplicationError) or cause.type != "FixturePermanentFailure":
                raise
            return FixtureResult(request.operation_id, "failed", None, cause.type,
                                 int(cause.details[0]), 0)

        if request.wait_for_release:
            self._waiting = True
            await workflow.wait_condition(lambda: self._released)
            self._waiting = False

        try:
            return await workflow.execute_activity(
                complete_fixture, prepared,
                start_to_close_timeout=timedelta(seconds=10),
                schedule_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except ActivityError as error:
            cause = error.cause
            if not isinstance(cause, ApplicationError) or cause.type != "FixtureUnknownDelivery":
                # Infrastructure errors and timeouts keep their native cause chain.
                raise
            return FixtureResult(request.operation_id, "unknown", None, cause.type,
                                 prepared.attempts, int(cause.details[0]))


@workflow.defn
class FixtureInvestigation:
    @workflow.run
    async def run(self, request: FixtureRequest) -> FixtureResult:
        return await workflow.execute_child_workflow(
            FixtureStage.run, request,
            id=f"{workflow.info().workflow_id}/fixture-stage",
            cancellation_type=workflow.ChildWorkflowCancellationType.WAIT_CANCELLATION_COMPLETED,
            parent_close_policy=workflow.ParentClosePolicy.REQUEST_CANCEL,
        )
