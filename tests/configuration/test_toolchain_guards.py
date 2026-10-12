"""Offline native report rejection guards; no runtime or application claims."""
from types import SimpleNamespace

import pytest

from tests.qualification.test_toolchains import native_report, expect_completed


@pytest.mark.parametrize('fault', ['missing', 'skip', 'wrong-id', 'failure', 'count', 'case-skipped'])
def test_nonexecuted_or_wrong_test_cannot_qualify_toolchain(fault):
    cases = '<testcase classname="fixture" name="expected"/>'
    attrs = 'tests="1" failures="0" errors="0" skipped="0"'
    if fault == 'missing':
        cases = ''
    elif fault == 'skip':
        attrs = attrs.replace('skipped="0"', 'skipped="1"')
    elif fault == 'wrong-id':
        cases = cases.replace('expected', 'other')
    elif fault == 'failure':
        attrs = attrs.replace('failures="0"', 'failures="1"')
    elif fault == 'count':
        attrs = attrs.replace('tests="1"', 'tests="2"')
    else:
        cases = '<testcase classname="fixture" name="expected"><skipped/></testcase>'
    with pytest.raises(AssertionError):
        native_report('<testsuite ' + attrs + '>' + cases + '</testsuite>', [('fixture', 'expected')])


def test_native_report_accepts_actual_expected_identifier():
    xml = '<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0"><testcase classname="fixture" name="expected"/></testsuite></testsuites>'
    assert native_report(xml, [('fixture', 'expected')])['tests'] == 1


@pytest.mark.parametrize('result', [SimpleNamespace(exit_code=0, stdout='version only', stderr=''), SimpleNamespace(exit_code=1, stdout='1 passed', stderr='')])
def test_version_or_exit_failure_cannot_substitute_for_successful_execution(result):
    with pytest.raises(AssertionError):
        expect_completed(result, 0, '1 passed')


@pytest.mark.parametrize('detail', ['http.client.RemoteDisconnected: Remote end closed connection without response', 'TimeoutError: timed out'])
@pytest.mark.parametrize('fault', ['no-event', 'old-event', 'other-sandbox', 'policy-denial', 'unrelated-error', 'wrong-destination', 'missing-event-id'])
def test_transport_error_requires_fresh_original_native_upstream_failure(fault, detail):
    from tests.qualification.test_toolchains import expect_registry_unavailable
    result = SimpleNamespace(exit_code=1, stdout='198.18.0.5\n', stderr=detail)
    event = {'metadata': {'uid': 'new'}, 'container': {'uid': 'owned'}, 'status_id': 2, 'class_uid': 4001, 'activity_id': 4, 'dst_endpoint': {'ip': '198.18.0.5', 'port': 5679}, 'message': 'Proxy connection error: Connection refused (os error 111)'}
    before = set()
    events = [event]
    if fault == 'no-event':
        events = []
    elif fault == 'old-event':
        before.add('new')
    elif fault == 'other-sandbox':
        event['container']['uid'] = 'other'
    elif fault == 'policy-denial':
        event['action_id'] = 2
    elif fault == 'wrong-destination':
        event['dst_endpoint']['ip'] = '198.18.0.6'
    elif fault == 'missing-event-id':
        del event['metadata']['uid']
    else:
        event['message'] = 'TLS or DNS failure'
    with pytest.raises(AssertionError):
        expect_registry_unavailable(result, events, before, 'owned')
