"""Deterministic fixture activities; no external resources or side effects.

Activity names are explicit and frozen replay contracts, independent of function names.
"""

from temporalio import activity
from temporalio.exceptions import ApplicationError

from .fixture_contracts import FixtureRequest, FixtureResult, PreparedFixture


@activity.defn(name="corsair.fixture.prepare")
async def prepare_fixture(request: FixtureRequest) -> PreparedFixture:
    attempt = activity.info().attempt
    if request.scenario == "permanent":
        raise ApplicationError("Fixture preparation refused", attempt,
                               type="FixturePermanentFailure", non_retryable=True)
    if request.scenario == "transient" and attempt < 3:
        raise ApplicationError("Fixture preparation temporarily unavailable",
                               type="FixtureTransientFailure")
    return PreparedFixture(request=request, attempts=attempt)


@activity.defn(name="corsair.fixture.complete")
async def complete_fixture(prepared: PreparedFixture) -> FixtureResult:
    request = prepared.request
    attempt = activity.info().attempt
    if request.scenario == "unknown":
        # Simulates unknown delivery; does not actually dispatch an external command.
        raise ApplicationError("Fixture delivery cannot be determined", attempt,
                               type="FixtureUnknownDelivery", non_retryable=True)
    return FixtureResult(request.operation_id, "completed", request.value, None,
                         prepared.attempts, attempt)
