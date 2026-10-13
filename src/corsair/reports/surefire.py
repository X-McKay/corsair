"""Bounded Maven Surefire XML parsing for JUnit tests; the report is a workload claim, never attestation.

Surefire writes one `TEST-<class>.xml` per test class. Ids are `[module/]package.Class#method`
(`ports.test_runner.JavaTestId`); the report names them by (classname, name).
"""
import re
import xml.etree.ElementTree as ET

from corsair.ports.test_runner import FailureDetail, JavaTestId, TestCaseResult
from corsair.reports.junit import MAX_JUNIT_BYTES, MAX_MESSAGE_CHARS, MAX_OUTPUT_CHARS, JUnitError, admit_xml

OUTCOMES = {'failure': 'failed', 'error': 'error', 'skipped': 'skipped'}
# Rerun and flaky elements mean Surefire retried a test; one execution is the contract, so they are refused.
CHILDREN = {*OUTCOMES, 'system-out', 'system-err'}
# `\tat [module/]package.Class.method(File.java:N)`; Surefire may trim the trace to the test class's frames.
FRAME = re.compile(r'\tat (?:[\w.$-]+(?:@[\w.-]+)?/)?(?P<class_name>[\w$]+(?:\.[\w$]+)*)\.(?P<method>[\w$<>]+)'
                   r'\((?P<file>[\w$]+\.java):(?P<line>\d+)\)')


class SurefireError(JUnitError):
    pass


def _function(method: str) -> str:
    """A lambda body `lambda$name$0` belongs to the test method `name`."""
    match = re.fullmatch(r'lambda\$(?P<name>[A-Za-z_]\w*)\$\d+', method)
    return match['name'] if match else method


def _failure(kind: str, element: ET.Element, frame_paths: dict[str, str]) -> FailureDetail:
    """Topmost frame declared in a patch test file plus Surefire's exception type."""
    location = None
    for line in (element.text or '').splitlines():
        match = FRAME.fullmatch(line)
        if match is None:
            continue
        package = match['class_name'].rpartition('.')[0]
        path = frame_paths.get(f'{package.replace(".", "/") + "/" if package else ""}{match["file"]}')
        if path is not None:
            location = path, _function(match['method']), int(match['line'])
            break
    path, function, line = location or (None, None, None)
    exception_type = element.get('type') or None
    message = element.get('message') or element.text or ''
    return FailureDetail(kind, exception_type, path, function, line, message[:MAX_MESSAGE_CHARS])


def parse_surefire(data: bytes, test_ids: tuple[str, ...], *, test_paths: frozenset[str],
                   test_root: str = 'src/test/java', max_bytes: int = MAX_JUNIT_BYTES) -> tuple[TestCaseResult, ...]:
    """Exactly one testcase per expected id, in the given order, from one class's report.

    `test_paths` are the patch's repository-relative files; frames map to them through Maven's test
    source root in the ids' module.
    """
    try:
        parsed = [JavaTestId.parse(test_id) for test_id in test_ids]
    except ValueError as error:
        raise SurefireError(str(error)) from error
    if len({(item.module, item.class_name) for item in parsed}) != 1:
        raise SurefireError('Expected test ids must share one module and class')
    keys = {(item.class_name, item.method): test_id for item, test_id in zip(parsed, test_ids)}
    if len(keys) != len(test_ids):
        raise SurefireError('Expected test ids are ambiguous in Surefire')
    module, class_name = parsed[0].module, parsed[0].class_name
    prefix = f'{module}/{test_root}/' if module else f'{test_root}/'
    frame_paths = {path.removeprefix(prefix): path for path in test_paths if path.startswith(prefix)}
    tree = admit_xml(data, max_bytes)
    if tree.tag != 'testsuite' or tree.get('name') != class_name:
        raise SurefireError('Expected the Surefire report of exactly the tests\' class')
    if any(child.tag not in ('properties', 'testcase', 'system-out', 'system-err') for child in tree):
        raise SurefireError('Unexpected element in Surefire testsuite')
    results = {}
    for case in tree.iter('testcase'):
        test_id = keys.get((case.get('classname'), case.get('name')))
        if test_id is None:
            raise SurefireError(f'Unexpected testcase {case.get("classname")!r}#{case.get("name")!r}')
        if test_id in results:
            raise SurefireError(f'Duplicate testcase {test_id}')
        if any(child.tag not in CHILDREN for child in case):
            raise SurefireError(f'Unexpected element in testcase {test_id}')
        marks = [child for child in case if child.tag in OUTCOMES]
        if len(marks) > 1:
            raise SurefireError(f'Ambiguous outcome for {test_id}')
        outcome = OUTCOMES[marks[0].tag] if marks else 'passed'
        failure = _failure(marks[0].tag, marks[0], frame_paths) if outcome in ('failed', 'error') else None
        output = ''.join(child.text or '' for child in case if child.tag == 'system-out')
        results[test_id] = TestCaseResult(test_id, outcome, failure, output[:MAX_OUTPUT_CHARS])
    if set(results) != set(test_ids):
        raise SurefireError(f'Missing testcases: {sorted(set(test_ids)-set(results))}')
    return tuple(results[test_id] for test_id in test_ids)
