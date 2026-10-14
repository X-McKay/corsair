"""The D8 probe outcome classifier (redesign section 13): a fixed truth table over facts trusted code observed.

No parser and no model: the exit class comes from the matrix row's exit-code map, the start and end marker files
are written by the test outside the output streams, and the token is a fresh per-run string the security
assertion uses as its failure message. The checks overlap on purpose, so a test that fakes one signal (exits 0
early, prints the token) disagrees with another and lands in ``anomalous`` rather than a decisive outcome.

The control probe carries no token, so a control whose assertion fails reads ``errored``. That is intended: only
the security assertion's failure is a decisive observation.
"""
from __future__ import annotations

from .contracts import ExitClass, Outcome, ProbeFacts


def classify(facts: ProbeFacts) -> Outcome:
    """Map one run's observed facts to its outcome; rows are checked top to bottom, the first match wins.

    | Exit class                            | start | end | token | Outcome            |
    | ------------------------------------- | ----- | --- | ----- | ------------------ |
    | none observed (timeout, no exit code) | any   | any | any   | ``infra``          |
    | no_tests, or no ``start``             | any   | any | any   | ``not_run``        |
    | harness_error                         | yes   | any | any   | ``infra``          |
    | pass                                  | yes   | yes | no    | ``passed``         |
    | test_failed                           | yes   | no  | yes   | ``assertion_failed`` |
    | test_failed                           | yes   | no  | no    | ``errored``        |
    | anything else (unknown code, pass without end, token on a pass, end after a failure) | | | | ``anomalous`` |

    A run with no exit code or a timeout has nothing trustworthy to read, so it is ``infra`` first. A missing
    ``start`` is checked before the harness class because a collection or compile error is the author's mechanics
    (``not_run``, which returns diagnostics under D3), not the platform's. A signal shows up as an exit code the
    row maps to ``harness_error``; a code the row does not list is ``unknown`` and never decisive.
    """
    if facts.timed_out or facts.exit_code is None:
        return Outcome.INFRA
    exit_class = facts.exit_class or ExitClass.UNKNOWN
    if exit_class is ExitClass.NO_TESTS or not facts.start_marker:
        return Outcome.NOT_RUN
    if exit_class is ExitClass.HARNESS_ERROR:
        return Outcome.INFRA
    if exit_class is ExitClass.PASS and facts.end_marker and not facts.token_in_output:
        return Outcome.PASSED
    if exit_class is ExitClass.TEST_FAILED and not facts.end_marker:
        return Outcome.ASSERTION_FAILED if facts.token_in_output else Outcome.ERRORED
    return Outcome.ANOMALOUS


def exit_class(exit_code: int | None, exit_codes: dict[int, ExitClass]) -> ExitClass | None:
    """The row's class for an exit code; None when no code was observed, ``unknown`` when the row does not list it."""
    if exit_code is None:
        return None
    return exit_codes.get(exit_code, ExitClass.UNKNOWN)
