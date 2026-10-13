"""Bounded parsing of one Perl test file's TAP stream (Test::More, stdout and stderr merged); a workload claim.

Ids are `path/to/file.t#subtest` (`ports.test_runner.PerlTestId`): exactly two top-level subtests, each announced by
its `# Subtest: <name>` line, and no other top-level test. Prove's own exit status and summary do not tell a pass
from a skip or a todo (SPEC-0056), so the stream itself is read: any todo is refused, a skip anywhere inside a
subtest makes it skipped, a bail-out or a skip-all plan is refused, and the exit status must agree with the outcomes.
"""
import re

from corsair.ports.test_runner import FailureDetail, PerlTestId, TestCaseResult
from corsair.reports.junit import MAX_JUNIT_BYTES, MAX_MESSAGE_CHARS, MAX_OUTPUT_CHARS, JUnitError

HEADER = re.compile(r'# Subtest: (?P<name>.+)')
RESULT = re.compile(r'(?P<not>not )?ok (?P<number>\d+)(?: - (?P<description>.*?))?'
                    r'(?:\s+#\s*(?P<directive>skip|todo)\b.*)?', re.IGNORECASE)
PLAN = re.compile(r'1\.\.(?P<count>\d+)(?P<rest>.*)')
NESTED_RESULT = re.compile(r'\s+(?:not )?ok\b.*')
NESTED_SKIP = re.compile(r'\s+(?:ok \d+.*#\s*skip\b|1\.\.0\s*#\s*skip\b).*', re.IGNORECASE)
NESTED_TODO = re.compile(r'\s+(?:not )?ok \d+.*#\s*todo\b.*', re.IGNORECASE)
LOCATION = re.compile(r'\s*#\s+at (?P<path>\S+) line (?P<line>\d+)\.')
DIAG = re.compile(r'\s*# ?(?P<text>.*)')
NO_TESTS = re.compile(r'No tests run for subtest "(?P<name>.*)"')


class TapError(JUnitError):
    pass


def _failure(kind, name, lines, test_paths):
    """First `at FILE line N.` in a patch file plus Test::More's diagnostics (got/expected, or a die message)."""
    path = line = None
    for text in lines:
        match = LOCATION.fullmatch(text)
        if match and match['path'] in test_paths:
            path, line = match['path'], int(match['line'])
            break
    message = '\n'.join(match['text'] if (match := DIAG.fullmatch(text)) else text for text in lines
                        if text.strip() and not NESTED_RESULT.fullmatch(text) and not text.strip().startswith('1..'))
    return FailureDetail(kind, 'die' if kind == 'error' else None, path, name, line, message[:MAX_MESSAGE_CHARS])


def parse_tap(data: bytes, test_ids: tuple[str, ...], *, exit_status: int, test_paths: frozenset[str],
              max_bytes: int = MAX_JUNIT_BYTES) -> tuple[TestCaseResult, ...]:
    """Exactly one top-level subtest result per expected id, in the given order, agreeing with the exit status."""
    try:
        parsed = [PerlTestId.parse(test_id) for test_id in test_ids]
    except ValueError as error:
        raise TapError(str(error)) from error
    if len({item.path for item in parsed}) != 1 or len({item.name for item in parsed}) != len(parsed):
        raise TapError('Expected test ids must be distinct subtests of one file')
    if len(data) > max_bytes:
        raise TapError('TAP stream exceeds the admitted size')
    try:
        lines = data.decode('utf-8').splitlines()
    except UnicodeError as error:
        raise TapError('TAP stream is not UTF-8') from error
    names = {item.name: test_id for item, test_id in zip(parsed, test_ids)}
    results, plans, header, block, last = {}, [], None, [], 0
    for index, text in enumerate(lines):
        if re.match(r'\s*Bail out!', text):
            raise TapError('Test file bailed out')
        if NESTED_TODO.fullmatch(text):
            raise TapError('A todo assertion hides its outcome')
        if (match := HEADER.fullmatch(text)) is not None:
            if header is not None:
                raise TapError(f'Subtest {header!r} has no result')
            header, block = match['name'], []
            continue
        if (match := PLAN.fullmatch(text)) is not None:
            if re.search(r'#\s*skip', match['rest'], re.IGNORECASE):
                raise TapError('Test file skipped all its tests')
            plans.append(int(match['count']))
            continue
        if (match := RESULT.fullmatch(text)) is None:
            if header is not None:
                block.append(text)
            continue
        if header is None:
            raise TapError(f'Top-level test outside a subtest: {text[:200]!r}')
        if int(match['number']) != last + 1:
            raise TapError('TAP test numbers are not sequential')
        last += 1
        test_id = names.get(header)
        if test_id is None:
            raise TapError(f'Unexpected subtest {header[:200]!r}')
        if test_id in results:
            raise TapError(f'Duplicate subtest {header[:200]!r}')
        directive = (match['directive'] or '').lower()
        if directive == 'todo':
            raise TapError('A todo subtest hides its outcome')
        if match['not']:
            died = NO_TESTS.fullmatch(match['description'] or '')
            if died and died['name'] != header:
                raise TapError('Subtest result names another subtest')
            # Diagnostics follow the result line up to the next subtest or plan (Test::More writes them after it).
            after = []
            for following in lines[index + 1:]:
                if HEADER.fullmatch(following) or PLAN.fullmatch(following) or RESULT.fullmatch(following):
                    break
                after.append(following)
            kind = 'error' if died else 'failure'
            results[test_id] = TestCaseResult(test_id, 'error' if died else 'failed',
                                              _failure(kind, header, block + after, test_paths),
                                              '\n'.join(block + after)[:MAX_OUTPUT_CHARS])
        else:
            skipped = directive == 'skip' or any(NESTED_SKIP.fullmatch(text) for text in block)
            results[test_id] = TestCaseResult(test_id, 'skipped' if skipped else 'passed', None,
                                              '\n'.join(block)[:MAX_OUTPUT_CHARS])
        header, block = None, []
    if set(results) != set(test_ids):
        raise TapError(f'Missing subtests: {sorted(set(test_ids) - set(results))}')
    errors = sum(case.outcome == 'error' for case in results.values())
    failed = sum(case.outcome in ('failed', 'error') for case in results.values())
    # Test::More exits with the number of failed tests, or 255 when the file died (its plan is then unfinished).
    if errors:
        if exit_status != 255:
            raise TapError(f'Exit {exit_status} conflicts with a subtest that died')
    elif plans != [len(test_ids)]:
        raise TapError(f'Expected exactly one plan of {len(test_ids)} tests, found {plans}')
    elif exit_status != failed:
        raise TapError(f'Exit {exit_status} conflicts with {failed} failed subtests')
    return tuple(results[test_id] for test_id in test_ids)
