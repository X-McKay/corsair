"""Bounded Jest `--json` report parsing; the report is a workload claim, never attestation.

Ids are `path::[suite::]name` (`ports.test_runner.JsTestId`); Jest names a test by its file (absolute
`name` of the test result), `ancestorTitles` and `title`. One run covers exactly one test file.
"""
import json
import re

from corsair.ports.test_runner import FailureDetail, JsTestId, TestCaseResult
from corsair.reports.admission import exactly, record
from corsair.reports.junit import MAX_JUNIT_BYTES, MAX_MESSAGE_CHARS, JUnitError

MAX_JEST_BYTES = MAX_JUNIT_BYTES
OUTCOMES = {'passed': 'passed', 'failed': 'failed', 'pending': 'skipped', 'skipped': 'skipped', 'todo': 'skipped',
            'disabled': 'skipped'}
# V8 stack frames `    at fn (/abs/file.js:L:C)` or `    at /abs/file.js:L:C`.
FRAME = re.compile(r' +at (?:[^()\n]+ \()?(?P<file>/[^():\n]+):(?P<line>\d+):(?P<column>\d+)\)?')
EXCEPTION = re.compile(r'(?P<type>[A-Za-z_$][\w$.]*)(?::|$)')


class JestError(JUnitError):
    pass


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise JestError('Duplicate JSON object key')
        result[key] = value
    return result


def admit_json(data: bytes, max_bytes: int = MAX_JEST_BYTES) -> dict:
    if type(data) is not bytes or not data or len(data) > max_bytes:
        raise JestError('Jest report outside the admitted byte envelope')
    try:
        report = json.loads(data.decode('utf-8'), object_pairs_hook=_unique_keys)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise JestError(f'Invalid Jest JSON report: {type(error).__name__}') from error
    if type(report) is not dict or type(report.get('testResults')) is not list:
        raise JestError('Expected a Jest aggregated result')
    return report


def _suite(report: dict, root: str, path: str) -> dict:
    """Exactly one test result, for exactly the selected file, that ran (a suite that failed to run has none)."""
    results = report['testResults']
    expected = root.rstrip('/') + '/' + path
    if len(results) != 1 or type(results[0]) is not dict or results[0].get('name') != expected:
        raise JestError(f'Expected the Jest result of exactly {path}')
    suite = results[0]
    tests = suite.get('assertionResults')
    if type(tests) is not list or not tests or report.get('numRuntimeErrorTestSuites') != 0:
        message = suite.get('message') if type(suite.get('message')) is str else ''
        raise JestError(f'Test suite failed to run: {message.strip()[:MAX_MESSAGE_CHARS]}')
    for test in tests:
        if (type(test) is not dict or type(test.get('title')) is not str or type(test.get('ancestorTitles')) is not list
                or any(type(title) is not str for title in test['ancestorTitles'])
                or type(test.get('status')) is not str or test['status'] not in OUTCOMES
                or type(test.get('failureMessages')) is not list):
            raise JestError('Malformed Jest assertion result')
    return suite


def listed(data: bytes, *, root: str, path: str, max_bytes: int = MAX_JEST_BYTES) -> tuple[str, ...] | None:
    """Ids of a listing run (every test filtered out, so none ran), or None when it is not exactly that.

    A test whose titles are not identifiers keeps its Jest full name, so it can never equal a requested id.
    """
    try:
        report = admit_json(data, max_bytes)
        tests = _suite(report, root, path)['assertionResults']
    except JestError:
        return None
    if report.get('success') is not True or any(test['status'] != 'pending' for test in tests):
        return None
    ids = []
    for test in tests:
        titles = [*test['ancestorTitles'], test['title']]
        candidate = '::'.join([path, *titles])
        try:
            ids.append(str(JsTestId.parse(candidate)))
        except ValueError:
            ids.append(f'{path}::{" ".join(titles)}')
    return tuple(ids)


def _failure(messages: list, root: str, test_paths: frozenset[str], name: str) -> FailureDetail:
    """Exception type from the first line; the topmost frame in a patch test file gives the line.

    Jest test bodies are anonymous callbacks, so the function is the test's own name when that frame exists.
    Jest 24 reports matcher failures (`expect(...)`) as `Error`.
    """
    text = messages[0] if messages and type(messages[0]) is str else ''
    lines = text.splitlines()
    match = EXCEPTION.match(lines[0]) if lines else None
    exception_type = match['type'] if match else None
    location = None
    for line in lines[1:]:
        frame = FRAME.fullmatch(line)
        if frame is None:
            continue
        path = frame['file'].removeprefix(root.rstrip('/') + '/')
        if path in test_paths:
            location = path, name, int(frame['line'])
            break
    path, function, line = location or (None, None, None)
    return FailureDetail('failure', exception_type, path, function, line, text[:MAX_MESSAGE_CHARS])


def parse_jest(data: bytes, test_ids: tuple[str, ...], *, root: str, test_paths: frozenset[str],
               max_bytes: int = MAX_JEST_BYTES) -> tuple[TestCaseResult, ...]:
    """Exactly one result per expected id, in the given order; every other test in the file was filtered out."""
    try:
        parsed = [JsTestId.parse(test_id) for test_id in test_ids]
    except ValueError as error:
        raise JestError(str(error)) from error
    if len({item.path for item in parsed}) != 1:
        raise JestError('Expected test ids must share one file')
    keys = {item.titles: test_id for item, test_id in zip(parsed, test_ids)}
    if len(keys) != len(test_ids):
        raise JestError('Expected test ids are ambiguous in Jest')
    report = admit_json(data, max_bytes)
    suite = _suite(report, root, parsed[0].path)
    results = {}
    for test in suite['assertionResults']:
        test_id = keys.get((tuple(test['ancestorTitles']), test['title']))
        if test_id is None:
            if test['status'] != 'pending':
                raise JestError(f'Unexpected test ran: {" ".join([*test["ancestorTitles"], test["title"]])!r}')
            continue
        outcome = OUTCOMES[test['status']]
        if (outcome == 'failed') != bool(test['failureMessages']):
            raise JestError(f'Outcome and failure messages disagree for {test_id}')
        failure = (_failure(test['failureMessages'], root, test_paths, JsTestId.parse(test_id).name)
                   if outcome == 'failed' else None)
        record(results, TestCaseResult(test_id, outcome, failure, ''), 'test', JestError)
    return exactly(results, test_ids, 'tests', JestError)
