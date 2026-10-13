"""Authoring's JavaScript assertion lines: where a Jest test fails on its own check, read with esprima."""
from pathlib import Path

import pytest

from corsair.agents.test_authoring.static import assertion_lines
from corsair.reports.jest import parse_jest

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / 'tests/unit/jest_reports'
CASES = ROOT / 'benchmarks/cases'


def test_jest_ids_read_javascript_and_others_stay_python():
    baseline = (REPORTS / 'baseline.test.js').read_text()
    assert assertion_lines(baseline, 'test/corsair.test.js::corsair_control') == (5,)
    assert assertion_lines(baseline, 'test/corsair.test.js::traversal::corsair_security') == (11,)
    assert assertion_lines('def test_x():\n    assert 1\n', 't.py::test_x') == (2,)


def test_the_line_jest_reports_for_a_matcher_failure_is_an_assertion_line():
    # The gate admits a security failure only at a planned assertion line; the real Jest 24 report names line 11.
    ids = ('test/corsair.test.js::corsair_control', 'test/corsair.test.js::traversal::corsair_security')
    _, security = parse_jest((REPORTS / 'node8-jest24.8.0-baseline-run.json').read_bytes(), ids, root='/sandbox/src',
                             test_paths=frozenset(['test/corsair.test.js']))
    assert security.failure.line in assertion_lines((REPORTS / 'baseline.test.js').read_text(), ids[1])


@pytest.mark.parametrize('case, path, security, control', [
    # The failing frame each case's baseline run reported (PLAN-0070): 23 inside the returned promise's callback.
    ('bestzip-command-injection/corsair.spec.js', 'test/corsair.spec.js', (23,), (12,)),
    ('codecov-gcov-command-injection/corsair.test.js', 'test/corsair.test.js', (27,), (18, 19, 20)),
])
def test_real_case_tests_name_the_lines_their_failures_were_reported_at(case, path, security, control):
    content = (CASES / case).read_text()
    assert assertion_lines(content, f'{path}::corsair_security') == security
    assert assertion_lines(content, f'{path}::corsair_control') == control


def test_matcher_chains_asserts_and_modules():
    suite = ("describe('traversal', () => {\n"
             "  it('corsair_security', async () => {\n"
             "    await expect(load('../x'))\n"
             "      .rejects.toThrow();\n"
             "    expect(1).not.toBe(2);\n"
             "    assert.strictEqual(read(), 'x');\n"
             "    assert(ok);\n"
             "    expect(value);\n"  # no matcher: not a check
             "  });\n"
             "});\n")
    assert assertion_lines(suite, 'test/a.test.js::traversal::corsair_security') == (3, 4, 5, 6, 7)
    module = "import x from 'y';\ntest('a', () => {\n  expect(x).toBe(1);\n});\n"
    assert assertion_lines(module, 'test/a.test.mjs::a') == (3,)


@pytest.mark.parametrize('content, test_id, message', [
    ("test('a' () => {});\n", 'test/a.test.js::a', 'does not parse'),
    ("test('a', () => {});\n", 'test/a.test.js::a', 'has no assertion'),
    ("test('a', () => { expect(1); });\n", 'test/a.test.js::a', 'has no assertion'),
    ("test('b', () => { expect(1).toBe(1); });\n", 'test/a.test.js::a', 'not defined'),
    ("test.skip('a', () => { expect(1).toBe(1); });\n", 'test/a.test.js::a', 'not defined'),
    ("describe('s', () => { test('a', () => { expect(1).toBe(1); }); });\n", 'test/a.test.js::a', 'not defined'),
    ("test('a', () => { expect(1).toBe(1); });\n", 'test/a.test.js::s::a', 'not defined'),
    ("test('a', () => { expect(1).toBe(1); });\ntest('a', () => { expect(2).toBe(2); });\n", 'test/a.test.js::a',
     'more than once'),
    ('x = [' * 5000, 'test/a.test.js::a', 'does not parse'),
])
def test_refusals(content, test_id, message):
    with pytest.raises(ValueError, match=message):
        assertion_lines(content, test_id)
