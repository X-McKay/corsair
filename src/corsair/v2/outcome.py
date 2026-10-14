"""The D8 probe outcome classifier (redesign section 13, with the SPEC-0082 review corrections): a fixed truth
table over facts trusted code observed.

No parser and no model: the exit class comes from the matrix row's exit-code map; the ``start``, ``check`` and
``end`` marker files are written by the test outside the output streams; the token is a fresh per-run string the
main assertion uses as its failure message. Both probes follow the same protocol, so the table is role-agnostic: a
control whose assertion fails reads ``assertion_failed`` like an exploit's, and Decide gives it its own meaning.

The token alone cannot attribute a failure, because repository code can read and print it. The ``check`` marker,
computed from the same condition the assertion checks and written immediately before it, says which way the
assertion went. The checks overlap on purpose, so a test that fakes one signal (exits 0 early, prints the token,
writes the wrong check) disagrees with another and lands in ``anomalous`` rather than a decisive outcome.
"""
from __future__ import annotations

from typing import Literal

from .contracts import ExitClass, Outcome, ProbeFacts

CHECK_VALUES = ("safe", "unsafe")


def classify(facts: ProbeFacts) -> Outcome:
    """Map one run's observed facts to its outcome; rows are read top to bottom, the first match wins.

    | Exit class                                   | start | end | token | check  | Outcome              |
    | -------------------------------------------- | ----- | --- | ----- | ------ | -------------------- |
    | timed out, no exit code, or harness_error    | any   | any | any   | any    | ``infra``            |
    | no_tests, or no ``start``                    | any   | any | any   | any    | ``not_run``          |
    | pass                                         | yes   | yes | no    | safe   | ``passed``           |
    | test_failed                                  | yes   | no  | yes   | unsafe | ``assertion_failed`` |
    | test_failed                                  | yes   | no  | no    | absent | ``errored``          |
    | anything else                                |       |     |       |        | ``anomalous``        |

    Infrastructure is read first: with no exit code, a timeout or a harness error there is nothing trustworthy to
    read. ``errored`` means the test failed before reaching its assertion (no check written). ``anomalous`` covers,
    for example, an unknown exit code, a pass without ``end`` or with the token or a check other than ``safe``, a
    failure that left ``end`` behind, a token without an ``unsafe`` check, and an ``unsafe`` check without a token.
    """
    exit_class = facts.exit_class or ExitClass.UNKNOWN
    if facts.timed_out or facts.exit_code is None or exit_class is ExitClass.HARNESS_ERROR:
        return Outcome.INFRA
    if exit_class is ExitClass.NO_TESTS or not facts.start_marker:
        return Outcome.NOT_RUN
    if (exit_class is ExitClass.PASS and facts.end_marker and not facts.token_in_output
            and facts.check_marker == "safe"):
        return Outcome.PASSED
    if exit_class is ExitClass.TEST_FAILED and not facts.end_marker:
        if facts.token_in_output and facts.check_marker == "unsafe":
            return Outcome.ASSERTION_FAILED
        if not facts.token_in_output and facts.check_marker is None:
            return Outcome.ERRORED
    return Outcome.ANOMALOUS


def exit_class(exit_code: int | None, exit_codes: dict[int, ExitClass]) -> ExitClass | None:
    """The row's class for an exit code; None when no code was observed, ``unknown`` when the row does not list it."""
    if exit_code is None:
        return None
    return exit_codes.get(exit_code, ExitClass.UNKNOWN)


def read_check(content: bytes | str | None) -> Literal["safe", "unsafe"] | None:
    """The check marker's value: its content with surrounding whitespace stripped, when that is exactly ``safe`` or
    ``unsafe``. An absent file, undecodable bytes or any other content is None."""
    if content is None:
        return None
    if isinstance(content, bytes):
        try:
            content = content.decode("utf-8")
        except UnicodeDecodeError:
            return None
    value = content.strip()
    return value if value in CHECK_VALUES else None  # type: ignore[return-value]
