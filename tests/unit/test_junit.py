"""Synthetic pytest-shaped JUnit; the parser classifies claims, it does not attest them."""
import pytest

from corsair.reports.junit import MAX_MESSAGE_CHARS, MAX_OUTPUT_CHARS, JUnitError, junit_key, parse_junit

IDS = ('tests/test_a.py::test_control', 'tests/test_a.py::TestSecurity::test_rejects')
PATHS = frozenset({'tests/test_a.py'})
TRACE = '''Traceback (most recent call last):
  File "/venv/lib/python3.12/site-packages/_pytest/python.py", line 166, in pytest_pyfunc_call
    result = testfunction(**testargs)
  File "/work/tests/test_a.py", line 12, in test_rejects
    helper()
  File "/work/tests/test_a.py", line 30, in helper
    assert opened is None, "security assertion"
  File "/work/app/documents.py", line 4, in read_document
    raise AssertionError("not reached by real pytest")
AssertionError: security assertion
  continued message
assert 'x' is None'''


def case(name, body='', classname='tests.test_a'):
    return f'<testcase classname="{classname}" name="{name}" time="0.001">{body}</testcase>'


def xml(*cases, root='testsuites'):
    inner = ''.join(cases) if root == 'testsuite' else '<testsuite name="pytest">'+''.join(cases)+'</testsuite>'
    return f'<?xml version="1.0" encoding="utf-8"?><{root}>{inner}</{root}>'.encode()


def parse(data, ids=IDS):
    return parse_junit(data, ids, root='/work', test_paths=PATHS)


def test_maps_node_ids_to_pytest_classname():
    assert junit_key('a/b/test_x.py::test_y') == ('a.b.test_x', 'test_y')
    assert junit_key('test_x.py::TestC::test_y') == ('test_x.TestC', 'test_y')
    with pytest.raises(JUnitError): junit_key('test_x.py::test_y[1]')


def test_classifies_outcomes_innermost_patch_frame_and_bounded_output():
    out = '<system-out>----- Captured Out -----\n{"test": "control"}\n</system-out><system-err>e</system-err>'
    data = xml(case('test_control', out),
               case('test_rejects', f'<failure message="AssertionError: security assertion">{TRACE}</failure>'
                    '<system-out>' + 'w'*(MAX_OUTPUT_CHARS+5) + '</system-out>', 'tests.test_a.TestSecurity'))
    control, security = parse(data)
    assert (control.test_id, control.outcome, control.failure) == (IDS[0], 'passed', None)
    assert '{"test": "control"}' in control.captured_output
    detail = security.failure
    assert security.outcome == 'failed' and len(security.captured_output) == MAX_OUTPUT_CHARS
    assert (detail.kind, detail.type, detail.path, detail.function, detail.line) == (
        'failure', 'AssertionError', 'tests/test_a.py', 'helper', 30)
    assert detail.message == 'AssertionError: security assertion'


def test_setup_error_skip_and_undeterminable_location():
    setup = '''Traceback (most recent call last):
  File "/work/tests/test_a.py", line 7, in files
    raise OSError("x")
OSError: x'''
    long = 'm'*(MAX_MESSAGE_CHARS+1)
    data = xml(case('test_control', f'<error message="failed on setup with &quot;OSError: x&quot;">{setup}</error>'),
               case('test_rejects', f'<failure message="{long}">no native frames here</failure>',
                    'tests.test_a.TestSecurity'), root='testsuite')
    control, security = parse(data)
    assert control.outcome == 'error'
    assert (control.failure.kind, control.failure.type, control.failure.path, control.failure.function,
            control.failure.line) == ('error', 'OSError', 'tests/test_a.py', 'files', 7)
    assert (security.failure.type, security.failure.path, security.failure.function, security.failure.line) == (None,)*4
    assert len(security.failure.message) == MAX_MESSAGE_CHARS
    skipped = parse(xml(case('test_control', '<skipped type="pytest.skip" message="r">t.py:1: r</skipped>'),
                        case('test_rejects', classname='tests.test_a.TestSecurity')))
    assert [c.outcome for c in skipped] == ['skipped', 'passed']


def test_frames_outside_patch_files_are_not_locations():
    trace = TRACE.replace('/work/tests/test_a.py', '/elsewhere/tests/test_a.py')
    data = xml(case('test_control', f'<failure message="m">{trace}</failure>'),
               case('test_rejects', classname='tests.test_a.TestSecurity'))
    failure = parse(data)[0].failure
    assert (failure.type, failure.path, failure.line) == ('AssertionError', None, None)


GOOD = (case('test_control'), case('test_rejects', classname='tests.test_a.TestSecurity'))


@pytest.mark.parametrize('data', [
    b'', b'\xff\xfe', b'<testsuites>', xml(*GOOD) + b'x'*262144,
    b'<?xml version="1.0"?><!DOCTYPE t [<!ENTITY a "aaaa">]><testsuites>&a;</testsuites>',
    b'<?xml version="1.0"?><!ENTITY a SYSTEM "file:///etc/passwd"><testsuites/>',
    xml(*GOOD, case('test_control')), xml(*GOOD, case('test_other')), xml(GOOD[0]),
    xml(case('test_control', classname='tests.test_b'), GOOD[1]),
    xml(case('test_control', '<failure message="a"/><error message="b"/>'), GOOD[1]),
    xml(case('test_control', '<rerun/>'), GOOD[1]), b'<report>' + xml(*GOOD)[38:] + b'</report>',
])
def test_rejects_unsafe_malformed_or_inexact_reports(data):
    with pytest.raises(JUnitError): parse(data)


def test_rejects_ambiguous_expected_ids():
    with pytest.raises(JUnitError): parse(xml(*GOOD), ('a/b.py::test_x', 'a.b.py::test_x'))
