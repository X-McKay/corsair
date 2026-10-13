"""Rules every framework's report shares before its outcomes become claims; reports are workload claims.

Each format reader (JUnit XML, Surefire XML, TAP, ...) only maps its own syntax to `TestCaseResult`s; the
envelope (bounded UTF-8), exactly one result per expected id in the expected order, and the refusal type
are the same for all of them. The runner checks the exit status against the admitted outcomes.
"""
from corsair.ports.test_runner import TestCaseResult


class ReportError(ValueError):
    """A report that cannot be admitted: no claim is made from it."""


def admit_text(data: bytes, max_bytes: int, what: str, error: type[ReportError] = ReportError) -> str:
    """Bounded, nonempty UTF-8."""
    if type(data) is not bytes or not 1 <= len(data) <= max_bytes:
        raise error(f'{what} outside the admitted byte envelope')
    try:
        return data.decode('utf-8')
    except UnicodeError as exc:
        raise error(f'{what} is not UTF-8') from exc


def record(results: dict[str, TestCaseResult], result: TestCaseResult, what: str,
           error: type[ReportError] = ReportError) -> None:
    """Add one result; a second result for the same id is a duplicate, never a retry to pick from."""
    if result.test_id in results:
        raise error(f'Duplicate {what} {result.test_id}')
    results[result.test_id] = result


def exactly(results: dict[str, TestCaseResult], test_ids: tuple[str, ...], what: str,
            error: type[ReportError] = ReportError) -> tuple[TestCaseResult, ...]:
    """One result per expected id, in the expected order; a missing one means nothing is claimed."""
    if set(results) != set(test_ids):
        raise error(f'Missing {what}: {sorted(set(test_ids) - set(results))}')
    return tuple(results[test_id] for test_id in test_ids)


def failed_count(cases: tuple[TestCaseResult, ...]) -> int:
    """Results that fail the claim (a failed assertion or an error); every framework's exit status counts these."""
    return sum(case.outcome in ('failed', 'error') for case in cases)
