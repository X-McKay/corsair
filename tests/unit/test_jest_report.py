"""Jest JSON report parsing against real Jest 24.8.0 output on Node 8.17.0 (see jest_reports/README.md)."""
import json
from pathlib import Path

import pytest

from corsair.reports.jest import JestError, listed, parse_jest

REPORTS = Path(__file__).with_name('jest_reports')
ROOT, PATH = '/sandbox/src', 'test/corsair.test.js'
PATHS = frozenset([PATH])
IDS = (PATH + '::corsair_control', PATH + '::traversal::corsair_security')
THROWN = (PATH + '::corsair_control', PATH + '::corsair_security')


def report(name):
    return (REPORTS / f'node8-jest24.8.0-{name}.json').read_bytes()


def test_listing_names_every_test_without_running_any():
    assert listed(report('baseline-listing'), root=ROOT, path=PATH) == IDS
    assert listed(report('syntax-listing'), root=ROOT, path=PATH) is None
    assert listed(report('nontest-listing'), root=ROOT, path='test/other.js') is None
    assert listed(report('baseline-listing'), root='/other', path=PATH) is None
    assert listed(report('baseline-run'), root=ROOT, path=PATH) is None


def test_listing_keeps_unaddressable_titles_unequal_to_ids():
    data = report('baseline-listing').replace(b'"title":"corsair_control"', b'"title":"corsair control"')
    assert listed(data, root=ROOT, path=PATH) == (PATH + '::corsair control', IDS[1])


def test_matcher_failure_maps_to_the_test_line():
    control, security = parse_jest(report('baseline-run'), IDS, root=ROOT, test_paths=PATHS)
    assert (control.outcome, control.failure) == ('passed', None)
    assert security.outcome == 'failed'
    assert (security.failure.type, security.failure.path, security.failure.function, security.failure.line) == (
        'Error', PATH, 'corsair_security', 11)
    assert security.failure.message.startswith('Error: expect(received).toBe(expected)')


def test_thrown_error_keeps_its_type():
    _, security = parse_jest(report('thrown-run'), THROWN, root=ROOT, test_paths=PATHS)
    assert (security.failure.type, security.failure.line) == ('TypeError', 7)


def test_frames_outside_patch_files_leave_the_location_unknown():
    _, security = parse_jest(report('baseline-run'), IDS, root=ROOT, test_paths=frozenset(['test/other.test.js']))
    assert (security.failure.path, security.failure.function, security.failure.line) == (None, None, None)


def test_candidate_passes():
    assert [c.outcome for c in parse_jest(report('candidate-run'), IDS, root=ROOT, test_paths=PATHS)] == ['passed', 'passed']


def test_pending_tests_are_skipped_claims():
    assert [c.outcome for c in parse_jest(report('baseline-listing'), IDS, root=ROOT, test_paths=PATHS)] == ['skipped', 'skipped']


def mutate(name, change):
    data = json.loads(report(name))
    change(data)
    return json.dumps(data).encode()


@pytest.mark.parametrize('data', [
    report('syntax-listing'),                                                                # suite failed to run
    report('nontest-listing'),                                                               # no result for the file
    mutate('baseline-run', lambda d: d['testResults'].append(dict(d['testResults'][0]))),   # two results
    mutate('baseline-run', lambda d: d['testResults'][0].update(name='/sandbox/src/test/other.test.js')),
    mutate('baseline-run', lambda d: d['testResults'][0]['assertionResults'].pop()),         # missing test
    mutate('baseline-run', lambda d: d['testResults'][0]['assertionResults'].append(
        dict(d['testResults'][0]['assertionResults'][0]))),                                 # duplicate
    mutate('baseline-run', lambda d: d['testResults'][0]['assertionResults'].append(
        {'ancestorTitles': [], 'title': 'extra', 'status': 'passed', 'failureMessages': []})),  # other test ran
    mutate('baseline-run', lambda d: d['testResults'][0]['assertionResults'][1].update(failureMessages=[])),
    mutate('baseline-run', lambda d: d['testResults'][0]['assertionResults'][1].update(status='weird')),
    mutate('baseline-run', lambda d: d['testResults'][0]['assertionResults'][1].update(status=[])),   # unhashable
    mutate('baseline-run', lambda d: d['testResults'][0]['assertionResults'][1].update(status={})),
    mutate('baseline-run', lambda d: d['testResults'][0]['assertionResults'][1].update(status=None)),
    mutate('baseline-run', lambda d: d.update(numRuntimeErrorTestSuites=1)),
    report('baseline-run').replace(b'{"numFailedTestSuites":1,', b'{"numFailedTestSuites":1,"numFailedTestSuites":1,'),
    b'not json', b'', b'[]',
])
def test_inexact_reports_are_refused(data):
    with pytest.raises(JestError):
        parse_jest(data, IDS, root=ROOT, test_paths=PATHS)


@pytest.mark.parametrize('status', [[], {}, None, 1])
def test_malformed_listing_status_is_not_a_listing(status):
    data = mutate('baseline-listing', lambda d: d['testResults'][0]['assertionResults'][0].update(status=status))
    assert listed(data, root=ROOT, path=PATH) is None


def test_oversize_reports_are_refused():
    with pytest.raises(JestError):
        parse_jest(report('baseline-run'), IDS, root=ROOT, test_paths=PATHS, max_bytes=100)


@pytest.mark.parametrize('ids', [(IDS[0], 'test/other.test.js::x'), (IDS[0], IDS[0]), ('tests/test_a.py::test_x', IDS[1])])
def test_expected_ids_must_be_distinct_jest_tests_of_one_file(ids):
    with pytest.raises(JestError):
        parse_jest(report('baseline-run'), ids, root=ROOT, test_paths=PATHS)
