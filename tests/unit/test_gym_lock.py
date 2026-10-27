"""The shared-root gym run lock: acquire, wait, stale reclaim, timeout and release.

Fake pids, a fake clock and a scratch gym root; no Temporal, Docker or model. The lock's
service path (two real runs, verify across both tiers) is covered by
tests/integration/test_gym_runner.py.
"""

import asyncio
import json
import logging
import socket
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from corsair.contracts import GateDecision
from corsair.entrypoints import gym
from corsair.settings import Settings
from tests.unit.evaluation.test_gym_gate import ALL, BASELINE
from tests.unit.test_gym_cli import _card

HOST = socket.gethostname()


def _holder(run_id: str = "gym-tier1-20261027t010000-aaaaaa", **update) -> gym.LockHolder:
    holder = gym.new_lock_holder(run_id, tier="tier1", branch="gym/h1", commit="c" * 40)
    return replace(holder, **update)


def _hold(root: Path, holder: gym.LockHolder) -> None:
    """Write a holder record as another process would have."""
    path = gym.lock_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(holder.record() | {"token": holder.token}))


class FakeTime:
    """A monotonic clock that advances only when the waiter sleeps."""

    def __init__(
        self, release_after: float | None = None, on_release: Callable[[], None] = lambda: None
    ) -> None:
        self.now = 1000.0
        self.slept: list[float] = []
        self.release_after = release_after
        self.on_release = on_release

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds
        if self.release_after is not None and self.now - 1000.0 >= self.release_after:
            self.on_release()
            self.release_after = None


def _waiting_lines(caplog) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.getMessage() == "gym.lock_waiting"]


@pytest.mark.asyncio
async def test_a_free_lock_is_taken_at_once_and_records_its_holder(tmp_path):
    holder = _holder()
    wait = await gym.acquire_lock(tmp_path, holder, timeout=10)

    assert (wait.waited_for, wait.reclaimed, wait.seconds) == ((), (), pytest.approx(0, abs=1))
    record = json.loads(gym.lock_file(tmp_path).read_text())
    assert gym.lock_file(tmp_path) == tmp_path / "lock/holder.json"
    assert record["run_id"] == holder.run_id
    assert record["pid"] == holder.pid and record["host"] == HOST
    assert (record["branch"], record["commit"], record["tier"]) == ("gym/h1", "c" * 40, "tier1")
    assert record["started_at"] == holder.started_at
    assert wait.record() == {
        "used": True,
        "holder_run_id": holder.run_id,
        "waited": False,
        "wait_seconds": 0.0,
        "waited_for": [],
        "reclaimed": [],
    }
    assert gym.release_lock(tmp_path, holder) is True
    assert not gym.lock_file(tmp_path).exists()
    assert gym.read_lock(tmp_path) is None


@pytest.mark.asyncio
async def test_a_live_holder_makes_the_caller_wait_with_a_line_every_minute(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="corsair")
    first = _holder("gym-tier1-20261027t010000-aaaaaa", pid=4242)
    _hold(tmp_path, first)
    clock = FakeTime(release_after=130.0, on_release=lambda: gym.lock_file(tmp_path).unlink())
    second = _holder("gym-tier0-20261027t010100-bbbbbb", tier="tier0")

    wait = await gym.acquire_lock(
        tmp_path,
        second,
        timeout=3600,
        alive=lambda pid: pid == 4242,
        clock=clock.clock,
        sleep=clock.sleep,
    )

    assert [item.run_id for item in wait.waited_for] == [first.run_id]
    assert wait.seconds == pytest.approx(130.0, abs=gym.LOCK_POLL_SECONDS)
    assert json.loads(gym.lock_file(tmp_path).read_text())["run_id"] == second.run_id
    assert max(clock.slept) <= gym.LOCK_POLL_SECONDS
    lines = _waiting_lines(caplog)
    # One line when the wait starts, then one per minute: at 0, 60 and 120 seconds.
    assert len(lines) == 3
    fields = [vars(record)["fields"] for record in lines]
    assert [item["run_id"] for item in fields] == [first.run_id] * 3
    assert [item["seconds"] for item in fields] == [0, 60, 120]
    assert fields[1]["message"].startswith(f"waiting for the gym lock held by {first.run_id}")
    record = wait.record()
    assert record["waited"] is True and record["wait_seconds"] == pytest.approx(130, abs=2)
    assert [item["run_id"] for item in record["waited_for"]] == [first.run_id]
    assert "token" not in record["waited_for"][0]


@pytest.mark.asyncio
async def test_a_holder_whose_process_is_gone_is_reclaimed_with_a_notice(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="corsair")
    stale = _holder("gym-tier1-20261027t000000-dddddd", pid=999_999)
    _hold(tmp_path, stale)
    holder = _holder("gym-tier0-20261027t010100-bbbbbb")

    wait = await gym.acquire_lock(tmp_path, holder, timeout=0, alive=lambda pid: False)

    assert [item.run_id for item in wait.reclaimed] == [stale.run_id]
    assert wait.waited_for == ()
    assert gym.read_lock(tmp_path) == holder
    (notice,) = [r for r in caplog.records if r.getMessage() == "gym.lock_reclaimed"]
    assert notice.levelno == logging.WARNING
    assert notice.fields["run_id"] == stale.run_id
    assert wait.record()["reclaimed"][0]["pid"] == 999_999


@pytest.mark.asyncio
async def test_an_unreadable_holder_record_is_reclaimed(tmp_path):
    gym.lock_file(tmp_path).parent.mkdir(parents=True)
    gym.lock_file(tmp_path).write_text("{not json")
    wait = await gym.acquire_lock(tmp_path, _holder(), timeout=0, alive=lambda pid: True)
    assert [item.run_id for item in wait.reclaimed] == ["unreadable"]


@pytest.mark.asyncio
async def test_a_holder_on_another_host_is_never_judged_stale(tmp_path):
    _hold(tmp_path, _holder(pid=1, host="elsewhere"))
    clock = FakeTime()
    with pytest.raises(gym.GymLockTimeout):
        await gym.acquire_lock(
            tmp_path,
            _holder("gym-x-20261027t010100-bbbbbb"),
            timeout=5,
            alive=lambda pid: False,
            clock=clock.clock,
            sleep=clock.sleep,
        )


@pytest.mark.asyncio
async def test_the_wait_ends_at_the_timeout_with_a_refusal_naming_the_holder(tmp_path):
    first = _holder("gym-tier1-20261027t010000-aaaaaa", pid=4242)
    _hold(tmp_path, first)
    clock = FakeTime()

    with pytest.raises(gym.GymLockTimeout) as refused:
        await gym.acquire_lock(
            tmp_path,
            _holder("gym-tier0-20261027t010100-bbbbbb"),
            timeout=300,
            alive=lambda pid: True,
            clock=clock.clock,
            sleep=clock.sleep,
        )

    assert isinstance(refused.value, gym.GymRefused)
    message = str(refused.value)
    assert first.run_id in message and "5m 00s" in message and "nothing was started" in message
    assert "--lock-timeout" in message and "gym lock release --force" in message
    assert clock.now - 1000.0 == pytest.approx(300.0)
    assert gym.read_lock(tmp_path) == first, "a refused waiter leaves the holder in place"


def test_release_removes_only_the_callers_own_lock_and_force_removes_any(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="corsair")
    first, other = _holder(), _holder("gym-other-20261027t010100-bbbbbb")
    _hold(tmp_path, first)

    assert gym.release_lock(tmp_path, other) is False
    assert gym.read_lock(tmp_path) == first
    assert any(record.getMessage() == "gym.lock_lost" for record in caplog.records)
    assert gym.force_release(tmp_path) == first
    assert gym.read_lock(tmp_path) is None
    assert gym.force_release(tmp_path) is None
    assert gym.release_lock(tmp_path, first) is False


@pytest.mark.asyncio
async def test_the_lock_scope_releases_on_failure_and_on_cancellation(tmp_path):
    holder = _holder()
    with pytest.raises(RuntimeError, match="run failed"):
        async with gym.gym_lock(tmp_path, holder, timeout=0):
            assert gym.read_lock(tmp_path) == holder
            raise RuntimeError("run failed")
    assert gym.read_lock(tmp_path) is None

    entered = asyncio.Event()

    async def interrupted() -> None:
        async with gym.gym_lock(tmp_path, holder, timeout=0):
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(interrupted())
    await entered.wait()
    assert gym.read_lock(tmp_path) == holder
    task.cancel()  # What asyncio.run does to the main task on SIGINT.
    with pytest.raises(asyncio.CancelledError):
        await task
    assert gym.read_lock(tmp_path) is None


def test_status_reports_the_holder_its_liveness_and_elapsed_time(tmp_path):
    assert gym.lock_status(tmp_path) is None
    holder = _holder(started_at="2026-10-27T01:00:00+00:00", pid=4242)
    _hold(tmp_path, holder)

    status = gym.lock_status(tmp_path, alive=lambda pid: True)
    assert status is not None
    assert status["run_id"] == holder.run_id and status["alive"] is True
    assert status["elapsed_seconds"] > 0
    assert gym.lock_status(tmp_path, alive=lambda pid: False)["alive"] is False  # ty: ignore[not-subscriptable]
    _hold(tmp_path, replace(holder, host="elsewhere"))
    assert gym.lock_status(tmp_path, alive=lambda pid: False)["alive"] is None  # ty: ignore[not-subscriptable]
    line = gym.lock_line({**status, "elapsed_seconds": 3725.0})
    assert line == (
        f"Gym lock: held by `{holder.run_id}` (tier1, gym/h1@ccccccc, pid 4242 on {HOST}, "
        "running) for 1h 02m 05s."
    )


def test_durations_read_as_hours_minutes_and_seconds():
    assert [gym.duration_text(s) for s in (0, 59.6, 60, 3599, 7200)] == [
        "0s",
        "1m 00s",
        "1m 00s",
        "59m 59s",
        "2h 00m 00s",
    ]


# verify holds one lock across both tiers


@pytest.mark.asyncio
async def test_verify_holds_one_lock_across_both_tiers(tmp_path, monkeypatch):
    settings = Settings(artifact_root=str(tmp_path / "artifacts"))
    gym_root = tmp_path / "artifacts/gym"
    reference = tmp_path / "reference"
    for tier in gym.VERIFY_TIERS:
        _card(reference / f"{tier}.json", BASELINE, run_id=f"ref-{tier}")
    seen: list[tuple[str, str | None, dict | None]] = []

    async def run_gym(options, *, root, compose_activities, observe, held=None, pinned=None):
        del root, compose_activities, observe, pinned
        tier = gym.tier_name(options.dataset)
        holder = gym.read_lock(gym_root)
        seen.append(
            (
                tier,
                None if holder is None else holder.run_id,
                None if held is None else held.record(),
            )
        )
        run_dir = tmp_path / "runs" / tier
        card = gym.read_scorecard(
            _card(run_dir / "scorecard.json", {**BASELINE, "py-b": ALL}, run_id=f"cand-{tier}")
        )
        return gym.GymRun(run_dir, card, [], "127.0.0.1:1", True, 1.0)

    monkeypatch.setattr(gym, "run_gym", run_gym)
    root = Path(__file__).resolve().parents[2]
    tiers = {name: root / f"evals/datasets/gym-{name}.json" for name in gym.VERIFY_TIERS}
    result = await gym.verify_candidate(
        gym.GymOptions(dataset=tiers["tier0"], settings=settings),
        reference,
        root=Path(__file__).resolve().parents[2],
        tiers=tiers,
    )

    assert result.decision is GateDecision.ACCEPTED
    verify_id = result.verdict_path.parent.name
    assert [(tier, holder) for tier, holder, _ in seen] == [
        ("tier0", verify_id),
        ("tier1", verify_id),
    ]
    tier0, tier1 = (record for _, _, record in seen)
    assert tier0 is not None and tier1 is not None
    assert tier0["holder_run_id"] == tier1["holder_run_id"] == verify_id
    assert tier1["waited"] is False and tier1["wait_seconds"] == 0.0
    assert gym.read_lock(gym_root) is None, "verify releases the lock when it ends"

    seen.clear()
    await gym.verify_candidate(
        gym.GymOptions(dataset=tiers["tier0"], settings=settings, lock=False),
        reference,
        root=Path(__file__).resolve().parents[2],
        tiers=tiers,
    )
    assert [(holder, record) for _, holder, record in seen] == [(None, None), (None, None)]
