"""Surefire parsing over real reports (tests/unit/surefire/README.md) plus synthetic refusals."""
from pathlib import Path

import pytest

from corsair.ports.test_runner import JavaTestId
from corsair.reports.surefire import SurefireError, parse_surefire
from corsair.reports import test_observations

REPORTS = Path(__file__).with_name('surefire')
WIKI = 'jspwiki-main/org.apache.wiki.BenchmarkWikiServletForwardingTest#'
WIKI_IDS = (WIKI + 'benignPageKeepsEncodedPageParameter', WIKI + 'inertWebRootResourceCannotSelectForwardTarget')
WIKI_PATHS = frozenset({'jspwiki-main/src/test/java/org/apache/wiki/BenchmarkWikiServletForwardingTest.java'})
SAMPLE = 'corsair.sample.DocumentsTest#'
SAMPLE_IDS = (SAMPLE + 'readsOrdinaryDocument', SAMPLE + 'refusesTraversalOutsideRoot')
SAMPLE_PATHS = frozenset({'src/test/java/corsair/sample/DocumentsTest.java'})


def report(name):
    return (REPORTS / name).read_bytes()


def outcomes(results):
    return [result.outcome for result in results]


def test_java_ids_are_module_aware_and_name_their_maven_source():
    item = JavaTestId.parse(WIKI_IDS[1])
    assert (item.module, item.class_name, item.method) == ('jspwiki-main', 'org.apache.wiki.BenchmarkWikiServletForwardingTest',
                                                           'inertWebRootResourceCannotSelectForwardTarget')
    assert item.source_path() in WIKI_PATHS and str(item) == WIKI_IDS[1]
    assert JavaTestId.parse('a/b.c/p.C#m').source_path('src/it/java') == 'a/b.c/src/it/java/p/C.java'
    assert JavaTestId.parse(SAMPLE_IDS[0]).module is None
    # The SPEC-0017 claim schema admits the Java form within the same bound.
    assert test_observations.TestClaim(test_id=WIKI_IDS[1], outcome='failed').test_id == WIKI_IDS[1]


@pytest.mark.parametrize('value', ['a/../b/C#m', '../C#m', './C#m', '-pl/C#m', 'a//C#m', 'C$Inner#m', 'C#m()',
                                   'C#m[1]', 'C', '#m', 'tests/test_a.py::test_x', 'p.C#m ', 'x/' * 70 + 'C#m'])
def test_java_ids_refuse_traversal_options_nesting_and_overlength(value):
    with pytest.raises(ValueError):
        JavaTestId.parse(value)


@pytest.mark.parametrize('name, expected', [
    ('jspwiki-baseline.xml', ['passed', 'failed']), ('jspwiki-candidate.xml', ['passed', 'passed']),
    ('jspwiki-baseline-surefire3.xml', ['passed', 'failed']), ('jspwiki-candidate-surefire3.xml', ['passed', 'passed'])])
def test_jspwiki_reports_from_both_surefire_versions(name, expected):
    results = parse_surefire(report(name), WIKI_IDS, test_paths=WIKI_PATHS)
    assert [r.test_id for r in results] == list(WIKI_IDS) and outcomes(results) == expected
    if expected[1] == 'failed':
        failure = results[1].failure
        assert (failure.kind, failure.type, failure.path, failure.function, failure.line) == (
            'failure', 'org.opentest4j.AssertionFailedError', next(iter(WIKI_PATHS)),
            'inertWebRootResourceCannotSelectForwardTarget', 63)
        assert failure.message.startswith('requested web-root resource selected as dispatcher target')
        assert 'BENCHMARK_SECURITY_FORWARD_URL=' in results[1].captured_output


def test_sample_failure_error_skip_and_output():
    control, security = parse_surefire(report('sample-documents.xml'), SAMPLE_IDS, test_paths=SAMPLE_PATHS)
    assert (control.outcome, control.captured_output) == ('passed', 'CONTROL_RESOLVED=/srv/documents/report.txt\n')
    assert (security.failure.path, security.failure.function, security.failure.line) == (
        'src/test/java/corsair/sample/DocumentsTest.java', 'refusesTraversalOutsideRoot', 21)
    broken = 'corsair.sample.BrokenTest#'
    error, skipped = parse_surefire(report('sample-broken.xml'), (broken + 'setupErrors', broken + 'skippedTest'),
                                    test_paths=frozenset({'src/test/java/corsair/sample/BrokenTest.java'}))
    # The innermost frame in the patch file is the helper, as for pytest; stderr is not captured output.
    assert (error.outcome, error.failure.type, error.failure.function, error.failure.line) == (
        'error', 'java.lang.IllegalStateException', 'helper', 11)
    assert error.captured_output == '' and skipped.outcome == 'skipped' and skipped.failure is None


def test_frames_outside_the_patch_leave_the_location_unknown():
    results = parse_surefire(report('sample-documents.xml'), SAMPLE_IDS, test_paths=frozenset({'src/test/java/Other.java'}))
    assert results[1].failure.path is None and results[1].failure.type == 'org.opentest4j.AssertionFailedError'


def test_junit4_report_under_surefire_2_22():
    legacy = 'corsair.sample.LegacyTest#'
    control, security = parse_surefire(report('junit4-legacy.xml'), (legacy + 'control', legacy + 'security'),
                                       test_paths=frozenset({'src/test/java/corsair/sample/LegacyTest.java'}))
    assert control.outcome == 'passed' and security.outcome == 'failed'
    assert (security.failure.type, security.failure.function, security.failure.line) == ('org.junit.ComparisonFailure', 'security', 8)
    assert security.captured_output == 'SECURITY_RAN\n'


def wrap(*cases, name='corsair.sample.DocumentsTest', extra=''):
    return (f'<?xml version="1.0" encoding="UTF-8"?><testsuite name="{name}" tests="2">{extra}'
            + ''.join(cases) + '</testsuite>').encode()


def case(method, body='', classname='corsair.sample.DocumentsTest'):
    return f'<testcase name="{method}" classname="{classname}" time="0.001">{body}</testcase>'


PASS = (case('readsOrdinaryDocument'), case('refusesTraversalOutsideRoot'))


@pytest.mark.parametrize('data, match', [
    (wrap(*PASS, name='corsair.sample.Other'), 'class'),
    (wrap(*PASS).replace(b'<testsuite ', b'<testsuites><testsuite ').replace(b'</testsuite>', b'</testsuite></testsuites>'), 'class'),
    (wrap(PASS[0]), 'Missing'),
    (wrap(*PASS, case('unrelatedThirdTest')), 'Unexpected testcase'),
    (wrap(*PASS, PASS[0]), 'Duplicate'),
    (wrap(PASS[0], case('refusesTraversalOutsideRoot', '<flakyFailure message="x"/>')), 'Unexpected element'),
    (wrap(PASS[0], case('refusesTraversalOutsideRoot', '<rerunFailure message="x"/><failure/>')), 'Unexpected element'),
    (wrap(PASS[0], case('refusesTraversalOutsideRoot', '<failure/><error/>')), 'Ambiguous'),
    (wrap(PASS[0], case('refusesTraversalOutsideRoot()')), 'Unexpected testcase'),
    (wrap(*PASS, extra='<testsuite name="nested"/>'), 'Unexpected element in Surefire testsuite'),
    (b'<!DOCTYPE x [<!ENTITY a "b">]>' + wrap(*PASS), 'declaration'),
    (b'\xff' + wrap(*PASS), 'UTF-8'),
    (wrap(*PASS)[:-5], 'Malformed'),
    (b'', 'envelope'),
])
def test_refuses_ambiguous_retried_foreign_or_unsafe_reports(data, match):
    # Every refusal is a JUnitError (a ValueError) that the runner records as an invalid report.
    with pytest.raises(ValueError, match=match):
        parse_surefire(data, SAMPLE_IDS, test_paths=SAMPLE_PATHS)


def test_ids_must_share_one_class_and_be_java_ids():
    with pytest.raises(SurefireError, match='one module and class'):
        parse_surefire(wrap(*PASS), (SAMPLE_IDS[0], 'corsair.sample.Other#x'), test_paths=SAMPLE_PATHS)
    with pytest.raises(SurefireError, match='one module and class'):
        parse_surefire(wrap(*PASS), (SAMPLE_IDS[0], 'app/' + SAMPLE_IDS[1]), test_paths=SAMPLE_PATHS)
    with pytest.raises(SurefireError):
        parse_surefire(wrap(*PASS), ('tests/test_a.py::test_x', SAMPLE_IDS[1]), test_paths=SAMPLE_PATHS)
    with pytest.raises(SurefireError, match='ambiguous'):
        parse_surefire(wrap(*PASS), (SAMPLE_IDS[0], SAMPLE_IDS[0]), test_paths=SAMPLE_PATHS)


def test_lambda_frames_belong_to_their_test_method_and_messages_are_bounded():
    trace = ('java.lang.AssertionError: x\n\tat corsair.sample.DocumentsTest.lambda$refusesTraversalOutsideRoot$0(DocumentsTest.java:22)\n'
             '\tat corsair.sample.DocumentsTest.refusesTraversalOutsideRoot(DocumentsTest.java:21)\n')
    data = wrap(PASS[0], case('refusesTraversalOutsideRoot', f'<failure message="{"m" * 5000}" type="java.lang.AssertionError">{trace}</failure>'))
    failure = parse_surefire(data, SAMPLE_IDS, test_paths=SAMPLE_PATHS)[1].failure
    assert (failure.function, failure.line, len(failure.message)) == ('refusesTraversalOutsideRoot', 22, 2048)
