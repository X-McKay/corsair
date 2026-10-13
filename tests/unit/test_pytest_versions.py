"""Runner discovery, JUnit parsing and baseline admission over real CPython 3.7 pytest 6.0-7.4 output (README.md)."""
from pathlib import Path

import pytest

from corsair.adapters.pytest_runner import collected
from corsair.agents.environment.frameworks import FRAMEWORKS
from corsair.reports.junit import parse_junit

REPORTS = Path(__file__).with_name('pytest_reports')
IDS = ('tests/test_case.py::test_control', 'tests/test_case.py::TestSecurity::test_security')
VERSIONS = ('6.0.2', '6.2.5', '7.0.1', '7.2.0', '7.4.4')


def output(version, kind):
    return (REPORTS / f'py37-pytest{version}-{kind}').read_bytes()


def test_every_recorded_version_is_covered():
    assert sorted(path.name for path in REPORTS.glob('py37-*')) == sorted(
        f'py37-pytest{v}-{kind}' for v in VERSIONS for kind in ('baseline.txt', 'collect.txt', 'junit.xml'))


@pytest.mark.parametrize('version', VERSIONS)
def test_discovery_parses_exactly_the_two_ids(version):
    # pytest 6.x lists importlib-mode items in another order; the runner compares sets.
    found = collected(output(version, 'collect.txt'))
    assert found is not None and sorted(found) == sorted(IDS)


@pytest.mark.parametrize('version', VERSIONS)
def test_junit_outcomes_and_failure_location(version):
    control, security = parse_junit(output(version, 'junit.xml'), IDS, root='/w',
                                    test_paths=frozenset({'tests/test_case.py'}))
    assert (control.outcome, control.failure) == ('passed', None)
    assert security.outcome == 'failed'
    failure = security.failure
    assert (failure.type, failure.path, failure.function, failure.line) == (
        'AssertionError', 'tests/test_case.py', 'test_security', 14)


@pytest.mark.parametrize('version', VERSIONS)
def test_baseline_summary_is_admitted(version):
    assert FRAMEWORKS['pytest'].passed(output(version, 'baseline.txt'))
