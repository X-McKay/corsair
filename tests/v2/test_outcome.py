"""The D8 truth table (redesign section 13 with the SPEC-0082 review corrections), row by row and exhaustively over
every fact combination."""
import itertools

import pytest

from corsair.v2.contracts import ExitClass, Outcome, ProbeFacts
from corsair.v2.outcome import classify, exit_class, read_check

E = ExitClass
O = Outcome  # noqa: E741

# (exit_code, exit_class, timed_out, start, end, token, check) -> outcome; every row of the table, then the
# anomalous combinations that matter (one faked or disagreeing signal each).
TABLE = [
    # infra first
    ((None, None, True, True, False, False, None), O.INFRA),  # timeout
    ((None, None, False, True, True, False, "safe"), O.INFRA),  # container failed, no exit code
    ((0, E.PASS, True, True, True, False, "safe"), O.INFRA),  # a timeout is never trusted, whatever else was seen
    ((2, E.HARNESS_ERROR, False, True, False, False, None), O.INFRA),
    ((2, E.HARNESS_ERROR, False, False, False, False, None), O.INFRA),  # infra outranks a missing start
    ((137, E.HARNESS_ERROR, False, True, True, True, "unsafe"), O.INFRA),  # a signal the row maps to harness_error
    # not_run
    ((5, E.NO_TESTS, False, True, True, False, "safe"), O.NOT_RUN),
    ((5, E.NO_TESTS, False, False, False, False, None), O.NOT_RUN),
    ((1, E.TEST_FAILED, False, False, False, False, None), O.NOT_RUN),  # compile or collection error
    ((0, E.PASS, False, False, True, False, "safe"), O.NOT_RUN),
    ((9, E.UNKNOWN, False, False, False, False, None), O.NOT_RUN),
    # the three exact rows
    ((0, E.PASS, False, True, True, False, "safe"), O.PASSED),
    ((1, E.TEST_FAILED, False, True, False, True, "unsafe"), O.ASSERTION_FAILED),  # either role's assertion
    ((1, E.TEST_FAILED, False, True, False, False, None), O.ERRORED),  # raised before the check marker
    # anomalous
    ((0, E.PASS, False, True, False, False, "safe"), O.ANOMALOUS),  # pass with no end: exited early
    ((0, E.PASS, False, True, True, True, "safe"), O.ANOMALOUS),  # token on a pass: printed outside the assertion
    ((0, E.PASS, False, True, True, False, "unsafe"), O.ANOMALOUS),  # passed although its check says unsafe
    ((0, E.PASS, False, True, True, False, None), O.ANOMALOUS),  # passed without writing a check
    ((1, E.TEST_FAILED, False, True, False, True, None), O.ANOMALOUS),  # token without a check: code printed it
    ((1, E.TEST_FAILED, False, True, False, True, "safe"), O.ANOMALOUS),  # failed although its check says safe
    ((1, E.TEST_FAILED, False, True, False, False, "unsafe"), O.ANOMALOUS),  # unsafe check but no token
    ((1, E.TEST_FAILED, False, True, False, False, "safe"), O.ANOMALOUS),  # failed after a safe check, no token
    ((1, E.TEST_FAILED, False, True, True, True, "unsafe"), O.ANOMALOUS),  # end after a failure: soft assertion
    ((1, E.TEST_FAILED, False, True, True, False, None), O.ANOMALOUS),
    ((9, E.UNKNOWN, False, True, True, False, "safe"), O.ANOMALOUS),  # unknown exit class is never decisive
    ((9, None, False, True, False, True, "unsafe"), O.ANOMALOUS),  # no class recorded reads as unknown
]


def facts(exit_code, cls, timed_out, start, end, token, check):
    return ProbeFacts(exit_code=exit_code, exit_class=cls, timed_out=timed_out, start_marker=start, end_marker=end,
                      token_in_output=token, check_marker=check)


@pytest.mark.parametrize(("row", "expected"), TABLE)
def test_table_rows(row, expected):
    assert classify(facts(*row)) is expected


ALL = list(itertools.product((None, 0), (None, *ExitClass), (False, True), (False, True), (False, True),
                             (False, True), (None, "safe", "unsafe")))


@pytest.mark.parametrize("row", ALL)
def test_every_combination_obeys_the_table(row):
    exit_code, cls, timed_out, start, end, token, check = row
    outcome = classify(facts(*row))
    effective = cls or E.UNKNOWN
    infra = exit_code is None or timed_out or effective is E.HARNESS_ERROR
    assert (outcome is O.INFRA) == infra
    if not infra:
        assert (outcome is O.NOT_RUN) == (effective is E.NO_TESTS or not start)
    ran = not infra and effective is not E.NO_TESTS and start
    # Only the exact rows give their outcome; everything else that ran is anomalous.
    assert (outcome is O.PASSED) == (ran and effective is E.PASS and end and not token and check == "safe")
    assert (outcome is O.ASSERTION_FAILED) == (ran and effective is E.TEST_FAILED and not end and token
                                               and check == "unsafe")
    assert (outcome is O.ERRORED) == (ran and effective is E.TEST_FAILED and not end and not token and check is None)


def test_exit_class_lookup():
    codes = {0: E.PASS, 1: E.TEST_FAILED}
    assert exit_class(0, codes) is E.PASS
    assert exit_class(3, codes) is E.UNKNOWN
    assert exit_class(None, codes) is None


@pytest.mark.parametrize(("content", "expected"), [
    (b"safe", "safe"), (b"unsafe\n", "unsafe"), ("  safe \r\n", "safe"), (None, None), (b"", None),
    (b"SAFE", None), (b"safe unsafe", None), (b"true", None), (b"\xff\xfe", None), (b"un safe", None)])
def test_read_check_accepts_only_safe_or_unsafe(content, expected):
    assert read_check(content) == expected
