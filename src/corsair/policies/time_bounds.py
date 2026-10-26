"""Every elapsed-time bound of one investigation, derived in one place. Pure.

The workflow schedules activities with these bounds, and the inference adapter sizes
the model episode and each provider request from the activity window it was given,
so the limits nest instead of racing::

    provider request <= model episode < activity window <= remaining investigation time

An episode that stops inside its activity returns a typed ``episode_timeout``
feedback with accounted usage; an activity that times out first is only an opaque
``ActivityError`` whose model usage is unknown. The activity values below are the
ones recorded in existing workflow histories: changing one alters scheduled
activity options and needs a ``workflow.patched`` gate.
"""

from __future__ import annotations

from dataclasses import dataclass

from corsair.contracts import Budget

PREPARE_ACTIVITY_SECONDS = 120
PRODUCER_ACTIVITY_SECONDS = 300
AUDITOR_ACTIVITY_SECONDS = 180
# Two sandboxed roles, each bounded by ``probe_timeout_seconds``, plus container
# creation, cleanup confirmation and receipt verification.
EVIDENCE_OVERHEAD_SECONDS = 45
RECORD_ATTEMPT_SECONDS = 30
# Includes queueing, retries and backoff of the idempotent final record.
RECORD_FINALIZATION_SECONDS = 90
MAX_HEARTBEAT_SECONDS = 15
# Workflow execution timeout beyond the action deadline: the final record must fit.
FINALIZATION_SLACK_SECONDS = 120
# Share of an activity window kept back from the model episode for building the
# agent, returning the typed output and serializing it; never more than 15 seconds.
EPISODE_RESERVE_FRACTION = 0.1
MAX_EPISODE_RESERVE_SECONDS = 15.0


@dataclass(frozen=True)
class EpisodeBounds:
    """Elapsed-time limits inside one model activity, in seconds."""

    episode_seconds: float
    request_seconds: float


def producer_activity_seconds(budget: Budget, elapsed_seconds: float) -> int:
    """The producer activity bound: its cap, or the investigation time that remains."""
    return min(PRODUCER_ACTIVITY_SECONDS, budget.max_elapsed_seconds - int(elapsed_seconds))


def evidence_activity_seconds(budget: Budget) -> int:
    """One differential run: both sandboxed roles plus fixed container overhead."""
    return 2 * budget.probe_timeout_seconds + EVIDENCE_OVERHEAD_SECONDS


def heartbeat_seconds(activity_seconds: int) -> int:
    """Heartbeat timeout of a bounded activity; model episodes heartbeat every 2 s."""
    return min(MAX_HEARTBEAT_SECONDS, activity_seconds)


def investigation_execution_seconds(budget: Budget) -> int:
    """Workflow execution timeout: the action deadline plus room for the final record."""
    return budget.max_elapsed_seconds + FINALIZATION_SLACK_SECONDS


def activity_window_seconds(
    start_to_close_seconds: float | None,
    schedule_to_close_seconds: float | None,
    queued_seconds: float,
) -> float | None:
    """Time left to a started activity attempt, from its server-side timeouts.

    A schedule-to-close bound also counts the time the task waited in the queue.
    Both inputs are server timestamps, so worker clock skew does not enter.
    """
    bounds = [start_to_close_seconds] if start_to_close_seconds else []
    if schedule_to_close_seconds:
        bounds.append(schedule_to_close_seconds - max(0.0, queued_seconds))
    return max(0.0, min(bounds)) if bounds else None


def episode_bounds(activity_seconds: float, request_timeout_seconds: float) -> EpisodeBounds:
    """Size a model episode strictly inside its activity window, and each request in it.

    The episode keeps back a reserve so it ends, and reports ``episode_timeout``,
    before the activity's own bound can fire. A configured provider-request timeout
    longer than the episode is lowered to it: a request cannot outlive its episode.
    """
    if activity_seconds <= 0:
        raise ValueError("a model activity window must be positive")
    if request_timeout_seconds <= 0:
        raise ValueError("a provider request timeout must be positive")
    reserve = min(MAX_EPISODE_RESERVE_SECONDS, activity_seconds * EPISODE_RESERVE_FRACTION)
    episode = activity_seconds - reserve
    return EpisodeBounds(
        episode_seconds=episode, request_seconds=min(request_timeout_seconds, episode)
    )
