"""Bounded JUnit XML parsing (pytest's report, and the reader Surefire's shares); a workload claim, never attestation."""
import re
from typing import Callable
import xml.etree.ElementTree as ET

from corsair.ports.test_runner import TEST_ID, FailureDetail, TestCaseResult
from corsair.reports.admission import ReportError, admit_text, exactly, record

MAX_JUNIT_BYTES = 262144
MAX_MESSAGE_CHARS = 2048
MAX_OUTPUT_CHARS = 8192
OUTCOMES = {'failure': 'failed', 'error': 'error', 'skipped': 'skipped'}
CHILDREN = {*OUTCOMES, 'system-out', 'system-err', 'properties'}
# `--tb=native` frames; the exception line is the first unindented line after the last frame.
FRAME = re.compile(r'  File "(?P<path>[^"\n]+)", line (?P<line>\d+), in (?P<function>[A-Za-z_<][\w<>.]*)')
EXCEPTION = re.compile(r'(?P<type>[A-Za-z_][\w.]*)(?::|$)')


class JUnitError(ReportError):
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


def admit_xml(data: bytes, max_bytes: int) -> ET.Element:
    """Bounded UTF-8 XML without any markup declaration (so no entity expansion), parsed by the stdlib."""
    text = admit_text(data, max_bytes, 'JUnit report', JUnitError)
    # Refuse every declaration (DOCTYPE, ENTITY, ...) before expat sees it: no entity expansion.
    if re.search(r'<!(?!--|\[CDATA\[)', text):
        raise JUnitError('JUnit report contains a markup declaration')
    try:
        return ET.fromstring(data)
    except ET.ParseError as error:
        raise JUnitError(f'Malformed JUnit report: {error}') from error


def parse_junit(data: bytes, test_ids: tuple[str, ...], *, root: str, test_paths: frozenset[str],
                max_bytes: int = MAX_JUNIT_BYTES) -> tuple[TestCaseResult, ...]:
    """Exactly one testcase per expected id, in the given order; anything else is invalid.

    `root` is the operator-known absolute workspace directory, stripped from native frame paths.
    """
    keys = {junit_key(test_id): test_id for test_id in test_ids}
    if len(keys) != len(test_ids):
        raise JUnitError('Expected test ids are ambiguous in JUnit')
    tree = admit_xml(data, max_bytes)
    if tree.tag not in ('testsuites', 'testsuite'):
        raise JUnitError('Unexpected JUnit root element')
    failure = lambda kind, element: _failure(kind, element, root, test_paths)
    return testcases(tree, keys, test_ids, children=CHILDREN, failure=failure, separator='::', error=JUnitError)


def testcases(tree: ET.Element, keys: dict[tuple[str, str], str], test_ids: tuple[str, ...], *, children: set[str],
              failure: Callable[[str, ET.Element], FailureDetail], separator: str,
              error: type[JUnitError]) -> tuple[TestCaseResult, ...]:
    """Every `testcase` keyed by (classname, name) must be an expected id with at most one outcome element."""
    results = {}
    for case in tree.iter('testcase'):
        test_id = keys.get((case.get('classname'), case.get('name')))
        if test_id is None:
            raise error(f'Unexpected testcase {case.get("classname")!r}{separator}{case.get("name")!r}')
        if test_id in results:
            raise error(f'Duplicate testcase {test_id}')
        if any(child.tag not in children for child in case):
            raise error(f'Unexpected element in testcase {test_id}')
        marks = [child for child in case if child.tag in OUTCOMES]
        if len(marks) > 1:
            raise error(f'Ambiguous outcome for {test_id}')
        outcome = OUTCOMES[marks[0].tag] if marks else 'passed'
        detail = failure(marks[0].tag, marks[0]) if outcome in ('failed', 'error') else None
        output = ''.join(child.text or '' for child in case if child.tag == 'system-out')
        record(results, TestCaseResult(test_id, outcome, detail, output[:MAX_OUTPUT_CHARS]), 'testcase', error)
    return exactly(results, test_ids, 'testcases', error)
