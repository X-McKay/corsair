"""Native activity test environment checks; these do not qualify persistence."""

import asyncio
from argparse import Namespace
from dataclasses import replace

import pytest
from temporalio.exceptions import ApplicationError
from temporalio.converter import DataConverter
from temporalio.testing import ActivityEnvironment

from corsair.workflows.fixture_activities import complete_fixture, prepare_fixture
from corsair.workflows.fixture_contracts import FixtureRequest
from tests.temporal.checkpoint import run


@pytest.mark.parametrize("kwargs", [
    {"operation_id": ""}, {"operation_id": "x" * 129},
    {"value": "é" * 2049}, {"scenario": "fallback"}, {"wait_for_release": 1},
])
def test_refuses_unbounded_or_implicit_inputs(kwargs):
    with pytest.raises(ValueError):
        FixtureRequest(**({"operation_id": "op", "value": "value"} | kwargs))


def test_native_activity_context_and_failure_metadata():
    async def check():
        env = ActivityEnvironment()
        request = FixtureRequest("op", "literal fixture", "transient")
        for attempt in (1, 2):
            env.info = replace(env.info, attempt=attempt)
            with pytest.raises(ApplicationError) as failure:
                await env.run(prepare_fixture, request)
            assert failure.value.type == "FixtureTransientFailure"
            assert not failure.value.non_retryable
        env.info = replace(env.info, attempt=3)
        prepared = await env.run(prepare_fixture, request)
        assert prepared.attempts == 3
        env.info = replace(env.info, attempt=1)
        result = await env.run(complete_fixture, prepared)
        assert result.outcome == "completed"
        assert result.value == request.value
        assert result.cleanup == "not_required"

        with pytest.raises(ApplicationError) as permanent:
            await env.run(prepare_fixture, FixtureRequest("op", "value", "permanent"))
        assert permanent.value.non_retryable
        assert permanent.value.type == "FixturePermanentFailure"
        assert permanent.value.details == (1,)

        prepared = await env.run(prepare_fixture, FixtureRequest("unknown-op", "value", "unknown"))
        with pytest.raises(ApplicationError) as unknown:
            await env.run(complete_fixture, prepared)
        assert unknown.value.non_retryable
        assert unknown.value.type == "FixtureUnknownDelivery"
        assert unknown.value.details == (1,)

    asyncio.run(check())


def test_native_default_converter_preserves_bounded_contract():
    async def check():
        original = FixtureRequest("op", "é" * 2048, "unknown", True)
        payloads = await DataConverter.default.encode([original])
        restored, = await DataConverter.default.decode(payloads, [FixtureRequest])
        assert restored == original
        assert len(restored.value.encode("utf-8")) == 4096
    asyncio.run(check())


def test_checkpoint_refuses_reused_evidence_before_connect(tmp_path, monkeypatch):
    async def unexpected_connect(*args, **kwargs):
        raise AssertionError("Existing evidence must refuse before a native connection")
    monkeypatch.setattr("tests.temporal.checkpoint.Client.connect", unexpected_connect)
    args = Namespace(phase="prepare", address="unused", identity="op", evidence_dir=str(tmp_path))
    with pytest.raises(FileExistsError):
        asyncio.run(run(args))
