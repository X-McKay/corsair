"""The D8 truth table (redesign section 13), row by row and exhaustively over every fact combination."""
import itertools

import pytest

from corsair.v2.contracts import ExitClass, Outcome, ProbeFacts
from corsair.v2.outcome import classify, exit_class

E = ExitClass
O = Outcome

# (exit_code, exit_class, timed_out, start, end, token) -> outcome; one line per row of the D8 table plus the
# examples the redesign names for `anomalous`.
TABLE = [
    ((0, E.PASS, False, True, True, False), O.PASSED),
    ((1, E.TEST_FAILED, False, True, False, True), O.ASSERTION_FAILED),
    ((1, E.TEST_FAILED, False, True, False, False), O.ERRORED),  # also a control whose assertion fails
    ((5, E.NO_TESTS, False, True, True, False), O.NOT_RUN),
    ((5, E.NO_TESTS, False, False, False, False), O.NOT_RUN),
    ((1, E.TEST_FAILED, False, False, False, False), O.NOT_RUN),  # compile or collection error
    ((0, E.PASS, False, False, True, False), O.NOT_RUN),
    ((2, E.HARNESS_ERROR, False, False, False, False), O.NOT_RUN),  # missing start outranks the harness class
    ((2, E.HARNESS_ERROR, False, True, False, False), O.INFRA),
    ((137, E.HARNESS_ERROR, False, True, True, True), O.INFRA),  # a signal the row maps to harness_error
    ((None, None, True, True, False, False), O.INFRA),  # timeout
    ((None, None, False, True, True, False), O.INFRA),  # container failed, no exit code
    ((0, E.PASS, True, True, True, False), O.INFRA),  # a timeout is never trusted, whatever else was seen
    ((0, E.PASS, False, True, False, False), O.ANOMALOUS),  # pass with no end: exited early
    ((0, E.PASS, False, True, True, True), O.ANOMALOUS),  # token on a pass: printed outside the assertion
    ((1, E.TEST_FAILED, False, True, True, True), O.ANOMALOUS),  # end after a failure: soft assertion
    ((1, E.TEST_FAILED, False, True, True, False), O.ANOMALOUS),
    ((9, E.UNKNOWN, False, True, True, False), O.ANOMALOUS),
    ((9, None, False, True, False, True), O.ANOMALOUS),  # no class recorded reads as unknown
]


def facts(exit_code, cls, timed_out, start, end, token):
    return ProbeFacts(exit_code=exit_code, exit_class=cls, timed_out=timed_out, start_marker=start, end_marker=end,
                      token_in_output=token)


@pytest.mark.parametrize(("row", "expected"), TABLE)
def test_table_rows(row, expected):
    assert classify(facts(*row)) is expected


ALL = list(itertools.product((None, 0), (None, *ExitClass), (False, True), (False, True), (False, True),
                             (False, True)))


@pytest.mark.parametrize("row", ALL)
def test_every_combination_obeys_the_table(row):
    exit_code, cls, timed_out, start, end, token = row
    outcome = classify(facts(*row))
    observed = exit_code is not None and not timed_out
    effective = cls or E.UNKNOWN
    if not observed:
        assert outcome is O.INFRA
    elif effective is E.NO_TESTS or not start:
        assert outcome is O.NOT_RUN
    elif effective is E.HARNESS_ERROR:
        assert outcome is O.INFRA
    # Only the two exact decisive rows are decisive; everything else is a non-decisive outcome.
    assert (outcome is O.PASSED) == (observed and effective is E.PASS and start and end and not token)
    assert (outcome is O.ASSERTION_FAILED) == (observed and effective is E.TEST_FAILED and start and not end and token)
    assert (outcome is O.ERRORED) == (observed and effective is E.TEST_FAILED and start and not end and not token)


def test_exit_class_lookup():
    codes = {0: E.PASS, 1: E.TEST_FAILED}
    assert exit_class(0, codes) is E.PASS
    assert exit_class(3, codes) is E.UNKNOWN
    assert exit_class(None, codes) is None
