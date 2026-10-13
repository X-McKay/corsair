"""The toolchain gate's TAP admission over real Perl 5.26.3 prove output (tap_reports/README.md)."""
from pathlib import Path

import pytest

from tests.qualification.prepare_toolchains import TAP_TESTS, tap_report

REPORTS = Path(__file__).with_name('tap_reports')


def output(kind):
    return (REPORTS / f'perl5.26.3-{kind}.txt').read_text()


def test_the_control_is_admitted_with_its_two_subtests():
    admitted = tap_report(output('control'), TAP_TESTS)
    assert admitted['tests'] == 2 and admitted['ids'] == ['native_roundtrip', 'native_runtime']


@pytest.mark.parametrize('kind', ['failure', 'skip', 'todo', 'notests'])
def test_failed_skipped_todo_and_empty_runs_are_refused(kind):
    # skip and todo end in prove's `Result: PASS` with exit 0; notests exits 0 too.
    with pytest.raises(AssertionError):
        tap_report(output(kind), TAP_TESTS)


def test_other_or_reordered_ids_are_refused():
    with pytest.raises(AssertionError):
        tap_report(output('control'), ('native_runtime', 'native_roundtrip'))
    with pytest.raises(AssertionError):
        tap_report(output('control'), TAP_TESTS[:1])
