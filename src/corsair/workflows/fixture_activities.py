"""Deterministic fixture activities; no external resources or side effects."""

from temporalio import activity
from temporalio.exceptions import ApplicationError

from .fixture_contracts import FixtureRequest, FixtureResult, PreparedFixture


@activity.defn
async def prepare_fixture(request: FixtureRequest) -> PreparedFixture:
    attempt = activity.info().attempt
    if request.scenario == "permanent":
        raise ApplicationError("Fixture preparation refused", attempt,
                               type="FixturePermanentFailure", non_retryable=True)
    if request.scenario == "transient" and attempt < 3:
        raise ApplicationError("Fixture preparation temporarily unavailable",
                               type="FixtureTransientFailure")
    return PreparedFixture(request=request, attempts=attempt)


@activity.defn
async def complete_fixture(prepared: PreparedFixture) -> FixtureResult:
    request = prepared.request
    attempt = activity.info().attempt
    if request.scenario == "unknown":
        # Simulates unknown delivery; does not actually dispatch an external command.
        raise ApplicationError("Fixture delivery cannot be determined", attempt,
                               type="FixtureUnknownDelivery", non_retryable=True)
    return FixtureResult(request.operation_id, "completed", request.value, None,
                         prepared.attempts, attempt)
