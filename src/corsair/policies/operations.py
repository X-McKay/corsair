"""The one rule naming evidence operations after their run, session and round.

The workflow assigns these ids when it schedules evidence; the external scorer
recomputes them to bind each saved receipt to the run, session and round that claim
it. Pure: no I/O, SDK or clock.
"""

from __future__ import annotations


def operation_prefix(run_id: str, session: int) -> str:
    """Session 1 keeps the original operation ids so earlier histories replay."""
    return run_id if session == 1 else f"{run_id}.s{session}"


def round_operation_id(run_id: str, session: int, index: int) -> str:
    """The vulnerable-revision evidence operation of one round of one session."""
    return f"{operation_prefix(run_id, session)}.r{index}"
