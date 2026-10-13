"""Bounded parsing of the runner's Minitest result report; the report is a workload claim, never attestation.

Minitest has no machine-readable report of its own. The Minitest runner's fixed Ruby script records each
result through Minitest's reporter API and prints one JSON document (`corsair-minitest-v1`); ids are
`path.rb::Class#test_method` (`ports.test_runner.RubyTestId`) and the report names them by (class, name).
"""
import json
import re

from corsair.ports.test_runner import FailureDetail, RubyTestId, TestCaseResult
from corsair.reports.junit import MAX_JUNIT_BYTES, MAX_MESSAGE_CHARS, JUnitError

SCHEMA = 'corsair-minitest-v1'
OUTCOMES = ('passed', 'failed', 'error', 'skipped')
MAX_FRAMES = 50
# Ruby backtrace lines, innermost first: `/ws/test/x_test.rb:7:in `test_x'` (3.3 and older) or
# `...:in 'Class#test_x'` (3.4); blocks appear as `block in test_x` or `block (2 levels) in test_x`.
FRAME = re.compile(r"(?P<path>[^:\n]+):(?P<line>\d+):in [`'](?:block (?:\(\d+ levels\) )?in )?"
                   r"(?:[A-Za-z_][\w:]*[#.])?(?P<function>[A-Za-z_][\w]*[?!=]?)'")


class MinitestReportError(JUnitError):
    pass


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise MinitestReportError('Duplicate key in Minitest report')
        result[key] = value
    return result


def _failure(detail, root: str, test_paths: frozenset[str]) -> FailureDetail:
    """Innermost frame inside a patch test file plus the exception class; None when undeterminable."""
    if (type(detail) is not dict or set(detail) != {'kind', 'type', 'message', 'backtrace'}
            or detail['kind'] not in ('failure', 'error') or type(detail['type']) is not str
            or type(detail['message']) is not str or type(detail['backtrace']) is not list
            or len(detail['backtrace']) > MAX_FRAMES or any(type(line) is not str for line in detail['backtrace'])):
        raise MinitestReportError('Malformed failure in Minitest report')
    location = None
    for line in detail['backtrace']:
        match = FRAME.fullmatch(line)
        if match is None:
            continue
        path = match['path'].removeprefix(root.rstrip('/') + '/')
        if path in test_paths:
            location = path, match['function'], int(match['line'])
            break
    path, function, line = location or (None, None, None)
    exception_type = detail['type'] if re.fullmatch(r'[A-Za-z_][\w:]*', detail['type']) else None
    return FailureDetail(detail['kind'], exception_type, path, function, line, detail['message'][:MAX_MESSAGE_CHARS])


def parse_minitest(data: bytes, test_ids: tuple[str, ...], *, root: str, test_paths: frozenset[str],
                   max_bytes: int = MAX_JUNIT_BYTES) -> tuple[TestCaseResult, ...]:
    """Exactly one result per expected id, in the given order, and nothing else."""
    try:
        parsed = [RubyTestId.parse(test_id) for test_id in test_ids]
    except ValueError as error:
        raise MinitestReportError(str(error)) from error
    keys = {(item.class_name, item.method): test_id for item, test_id in zip(parsed, test_ids)}
    if len(keys) != len(test_ids):
        raise MinitestReportError('Expected test ids are ambiguous in Minitest')
    if type(data) is not bytes or not 1 <= len(data) <= max_bytes:
        raise MinitestReportError('Minitest report outside the admitted byte envelope')
    try:
        document = json.loads(data.decode('utf-8'), object_pairs_hook=_unique)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise MinitestReportError(f'Invalid Minitest report: {error}') from error
    if type(document) is not dict or set(document) != {'schema', 'tests'} or document['schema'] != SCHEMA \
            or type(document['tests']) is not list:
        raise MinitestReportError('Expected one corsair-minitest-v1 report')
    results = {}
    for item in document['tests']:
        if type(item) is not dict or set(item) != {'class', 'name', 'outcome', 'failure'}:
            raise MinitestReportError('Malformed result in Minitest report')
        test_id = keys.get((item['class'], item['name']))
        if test_id is None:
            raise MinitestReportError(f'Unexpected result {item["class"]!r}#{item["name"]!r}')
        if test_id in results:
            raise MinitestReportError(f'Duplicate result {test_id}')
        outcome = item['outcome']
        if outcome not in OUTCOMES or (item['failure'] is None) != (outcome in ('passed', 'skipped')):
            raise MinitestReportError(f'Ambiguous outcome for {test_id}')
        failure = None if item['failure'] is None else _failure(item['failure'], root, test_paths)
        if failure is not None and failure.kind != ('error' if outcome == 'error' else 'failure'):
            raise MinitestReportError(f'Failure kind conflicts with outcome for {test_id}')
        results[test_id] = TestCaseResult(test_id, outcome, failure, '')
    if set(results) != set(test_ids):
        raise MinitestReportError(f'Missing results: {sorted(set(test_ids) - set(results))}')
    return tuple(results[test_id] for test_id in test_ids)
