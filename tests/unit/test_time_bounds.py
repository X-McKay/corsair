"""One source of truth for activity, model-episode and provider-request time bounds."""

from __future__ import annotations

import dataclasses
import time
from datetime import timedelta
from pathlib import Path
from typing import cast

import pytest
from temporalio.testing import ActivityEnvironment

from corsair.adapters.inference.adk import run_auditor, run_producer
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import AuditInput, AuditOutput, Budget, ProducerInput, ProducerOutput, Usage
from corsair.policies import time_bounds
from corsair.policies.time_bounds import (
    AUDITOR_ACTIVITY_SECONDS,
    PRODUCER_ACTIVITY_SECONDS,
    RECORD_FINALIZATION_SECONDS,
    activity_window_seconds,
    episode_bounds,
    evidence_activity_seconds,
    heartbeat_seconds,
    investigation_execution_seconds,
    producer_activity_seconds,
)
from corsair.ports.sandboxing import SandboxPort
from corsair.ports.scm import SourceSnapshotPort
from corsair.settings import ModelSettings, Settings
from corsair.steps.activities import Activities
from tests.unit.adk import ScriptedLlm, StalledLlm, text_response
from tests.unit.test_agents import _audit_input, _producer_input

WINDOWS = [0.5, 1, 2, 9.5, 10, 29, 30, 100, 150, 165, 180, 299, 300, 3600]
REQUESTS = [1, 2, 17, 120, 150, 299, 300]


def test_recorded_activity_bounds_are_pinned_because_histories_replay_them():
    # These are the values in recorded workflow histories. Changing any of them
    # changes scheduled activity options and needs a workflow.patched gate.
    assert (
        time_bounds.PREPARE_ACTIVITY_SECONDS,
        PRODUCER_ACTIVITY_SECONDS,
        AUDITOR_ACTIVITY_SECONDS,
        time_bounds.EVIDENCE_OVERHEAD_SECONDS,
        time_bounds.RECORD_ATTEMPT_SECONDS,
        RECORD_FINALIZATION_SECONDS,
        time_bounds.MAX_HEARTBEAT_SECONDS,
        time_bounds.FINALIZATION_SLACK_SECONDS,
    ) == (120, 300, 180, 45, 30, 90, 15, 120)


def test_request_never_outlives_episode_and_episode_ends_inside_its_activity():
    for window in WINDOWS:
        for request_timeout in REQUESTS:
            bounds = episode_bounds(window, request_timeout)

            assert 0 < bounds.request_seconds <= bounds.episode_seconds < window
            assert bounds.request_seconds == min(request_timeout, bounds.episode_seconds)
            assert window - bounds.episode_seconds <= time_bounds.MAX_EPISODE_RESERVE_SECONDS


def test_live_defaults_bound_one_request_inside_each_role_activity():
    # The live profile configures a 300 s request timeout on a thinking model.
    producer = episode_bounds(PRODUCER_ACTIVITY_SECONDS, 300)
    auditor = episode_bounds(AUDITOR_ACTIVITY_SECONDS, 300)

    assert (producer.episode_seconds, producer.request_seconds) == (285, 285)
    assert (auditor.episode_seconds, auditor.request_seconds) == (165, 165)
    assert episode_bounds(PRODUCER_ACTIVITY_SECONDS, 120).request_seconds == 120


@pytest.mark.parametrize(("window", "request_timeout"), [(0, 120), (-1, 120), (30, 0)])
def test_episode_bounds_reject_an_empty_window_or_request(window: float, request_timeout: int):
    with pytest.raises(ValueError):
        episode_bounds(window, request_timeout)


def test_producer_activity_never_exceeds_its_cap_or_the_remaining_budget():
    for max_elapsed in (30, 60, 299, 300, 900, 3600):
        for elapsed in (0, 0.9, 1, 29, 250.5):
            budget = Budget(max_elapsed_seconds=max_elapsed)
            seconds = producer_activity_seconds(budget, elapsed)

            assert seconds <= PRODUCER_ACTIVITY_SECONDS
            assert seconds <= max_elapsed - int(elapsed)
            assert seconds == min(300, max_elapsed - int(elapsed))


@pytest.mark.parametrize("probe", [1, 30, 300])
def test_evidence_heartbeat_and_execution_bounds_nest(probe: int):
    budget = Budget(probe_timeout_seconds=probe, max_elapsed_seconds=900)

    assert evidence_activity_seconds(budget) > 2 * probe
    for seconds in (1, 15, 16, 120, 300):
        assert heartbeat_seconds(seconds) <= min(seconds, 15)
    assert investigation_execution_seconds(budget) > (
        budget.max_elapsed_seconds + RECORD_FINALIZATION_SECONDS
    )


def test_activity_window_counts_queueing_against_schedule_to_close():
    assert activity_window_seconds(300, 300, 0) == 300
    assert activity_window_seconds(300, 300, 12.5) == 287.5
    assert activity_window_seconds(30, 90, 5) == 30
    assert activity_window_seconds(300, 300, 400) == 0
    assert activity_window_seconds(None, 300, 10) == 290
    assert activity_window_seconds(300, None, 10) == 300
    assert activity_window_seconds(None, None, 0) is None


class _RecordingInference:
    def __init__(self) -> None:
        self.windows: list[float | None] = []

    async def produce(
        self, request: ProducerInput, *, window_seconds: float | None = None
    ) -> ProducerOutput:
        del request
        self.windows.append(window_seconds)
        return ProducerOutput(usage=Usage())

    async def audit(
        self, request: AuditInput, *, window_seconds: float | None = None
    ) -> AuditOutput:
        del request
        self.windows.append(window_seconds)
        return AuditOutput(usage=Usage())


@pytest.mark.asyncio
async def test_model_activities_pass_their_scheduled_window_to_inference(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    inference = _RecordingInference()
    activities = Activities(
        Settings(),
        store=store,
        inference=inference,
        sources=cast(SourceSnapshotPort, object()),
        sandbox=cast(SandboxPort, object()),
    )
    environment = ActivityEnvironment()
    info = environment.info
    environment.info = dataclasses.replace(
        info,
        start_to_close_timeout=timedelta(seconds=180),
        schedule_to_close_timeout=timedelta(seconds=180),
        started_time=info.current_attempt_scheduled_time + timedelta(seconds=4),
    )

    await environment.run(activities.produce, _producer_input(store))
    await environment.run(activities.audit, _audit_input(store))

    assert inference.windows == [176, 176]


@pytest.mark.asyncio
async def test_slow_producer_episode_stops_inside_the_given_window(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    model = StalledLlm(model="stalled-provider")
    started = time.monotonic()

    output = await run_producer(
        _producer_input(store), ModelSettings(), store, model, window_seconds=1.0
    )

    assert time.monotonic() - started < 1.0
    assert output.feedback is not None
    assert (output.feedback.gate, output.feedback.operational) == ("episode_timeout", True)
    assert output.usage.llm_calls == 1 == len(model.requests)
    assert output.decision is None


@pytest.mark.asyncio
async def test_slow_auditor_episode_stops_inside_the_given_window(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    model = StalledLlm(model="stalled-provider")
    started = time.monotonic()

    output = await run_auditor(_audit_input(store), ModelSettings(), model, window_seconds=1.0)

    assert time.monotonic() - started < 1.0
    assert output.feedback is not None
    assert (output.feedback.gate, output.feedback.operational) == ("episode_timeout", True)
    assert output.usage.llm_calls == 1 == len(model.requests)
    assert output.review is None


@pytest.mark.parametrize(("role", "window"), [("producer", 300), ("auditor", 180)])
@pytest.mark.asyncio
async def test_litellm_request_timeout_is_lowered_to_the_episode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, role: str, window: int
):
    import google.adk.models as adk_models

    timeouts: list[float] = []

    class FakeLiteLlm(ScriptedLlm):
        def __init__(self, **kwargs):
            timeouts.append(kwargs["timeout"])
            super().__init__(model=kwargs["model"], responses=[text_response("{}")])

    monkeypatch.setitem(vars(adk_models), "LiteLlm", FakeLiteLlm)
    settings = ModelSettings(
        connector="litellm",
        producer="hosted_vllm/example",
        auditor="hosted_vllm/example",
        request_timeout_seconds=300,
    )
    store = ArtifactStore(tmp_path)
    if role == "producer":
        await run_producer(_producer_input(store), settings, store, window_seconds=window)
    else:
        await run_auditor(_audit_input(store), settings, window_seconds=window)

    assert timeouts == [episode_bounds(window, 300).request_seconds]
