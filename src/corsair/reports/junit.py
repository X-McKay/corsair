"""Bounded pytest JUnit XML parsing; the XML is a workload claim, never attestation."""
import re
import xml.etree.ElementTree as ET

from corsair.ports.test_runner import TEST_ID, FailureDetail, TestCaseResult

MAX_JUNIT_BYTES = 262144
MAX_MESSAGE_CHARS = 2048
MAX_OUTPUT_CHARS = 8192
OUTCOMES = {'failure': 'failed', 'error': 'error', 'skipped': 'skipped'}
CHILDREN = {*OUTCOMES, 'system-out', 'system-err', 'properties'}
# `--tb=native` frames; the exception line is the first unindented line after the last frame.
FRAME = re.compile(r'  File "(?P<path>[^"\n]+)", line (?P<line>\d+), in (?P<function>[A-Za-z_<][\w<>.]*)')
EXCEPTION = re.compile(r'(?P<type>[A-Za-z_][\w.]*)(?::|$)')


class JUnitError(ValueError):
    pass


def junit_key(test_id: str) -> tuple[str, str]:
    """pytest's (classname, name) for `path.py::name` or `path.py::Class::name`."""
    if not TEST_ID.fullmatch(test_id):
        raise JUnitError('Expected a plain pytest node id')
    path, *parts = test_id.split('::')
    return '.'.join([path.removesuffix('.py').replace('/', '.'), *parts[:-1]]), parts[-1]


def _failure(kind: str, element: ET.Element, root: str, test_paths: frozenset[str]) -> FailureDetail:
    """Innermost frame inside a patch test file plus the final exception type; None when undeterminable."""
    lines = (element.text or '').splitlines()
    frames = [(index, FRAME.fullmatch(line)) for index, line in enumerate(lines)]
    frames = [(index, match) for index, match in frames if match]
    location = None
    for _, match in reversed(frames):
        path = match['path'].removeprefix(root.rstrip('/') + '/')
        if path in test_paths:
            location = path, match['function'], int(match['line'])
            break
    exception_type = None
    if frames:
        tail = next((line for line in lines[frames[-1][0]+1:] if line and not line[0].isspace()), '')
        match = EXCEPTION.match(tail)
        exception_type = match['type'] if match else None
    path, function, line = location or (None, None, None)
    message = element.get('message') or element.text or ''
    return FailureDetail(kind, exception_type, path, function, line, message[:MAX_MESSAGE_CHARS])


def parse_junit(data: bytes, test_ids: tuple[str, ...], *, root: str, test_paths: frozenset[str],
                max_bytes: int = MAX_JUNIT_BYTES) -> tuple[TestCaseResult, ...]:
    """Exactly one testcase per expected id, in the given order; anything else is invalid.

    `root` is the operator-known absolute workspace directory, stripped from native frame paths.
    """
    if type(data) is not bytes or not 1 <= len(data) <= max_bytes:
        raise JUnitError('JUnit report outside the admitted byte envelope')
    try:
        text = data.decode('utf-8')
    except UnicodeError as error:
        raise JUnitError('JUnit report is not UTF-8') from error
    # Refuse every declaration (DOCTYPE, ENTITY, ...) before expat sees it: no entity expansion.
    if re.search(r'<!(?!--|\[CDATA\[)', text):
        raise JUnitError('JUnit report contains a markup declaration')
    keys = {junit_key(test_id): test_id for test_id in test_ids}
    if len(keys) != len(test_ids):
        raise JUnitError('Expected test ids are ambiguous in JUnit')
    try:
        tree = ET.fromstring(data)
    except ET.ParseError as error:
        raise JUnitError(f'Malformed JUnit report: {error}') from error
    if tree.tag not in ('testsuites', 'testsuite'):
        raise JUnitError('Unexpected JUnit root element')
    results = {}
    for case in tree.iter('testcase'):
        test_id = keys.get((case.get('classname'), case.get('name')))
        if test_id is None:
            raise JUnitError(f'Unexpected testcase {case.get("classname")!r}::{case.get("name")!r}')
        if test_id in results:
            raise JUnitError(f'Duplicate testcase {test_id}')
        if any(child.tag not in CHILDREN for child in case):
            raise JUnitError(f'Unexpected element in testcase {test_id}')
        marks = [child for child in case if child.tag in OUTCOMES]
        if len(marks) > 1:
            raise JUnitError(f'Ambiguous outcome for {test_id}')
        outcome = OUTCOMES[marks[0].tag] if marks else 'passed'
        failure = _failure(marks[0].tag, marks[0], root, test_paths) if outcome in ('failed', 'error') else None
        output = ''.join(child.text or '' for child in case if child.tag == 'system-out')
        results[test_id] = TestCaseResult(test_id, outcome, failure, output[:MAX_OUTPUT_CHARS])
    if set(results) != set(test_ids):
        raise JUnitError(f'Missing testcases: {sorted(set(test_ids)-set(results))}')
    return tuple(results[test_id] for test_id in test_ids)
