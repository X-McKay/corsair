"""Per-call model and tool telemetry on the canonical ``Usage`` record."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from pydantic import ValidationError

from corsair.adapters.inference.adk import _EpisodeAccounting, run_auditor, run_producer
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import ProducerOutput, Usage
from corsair.contracts.common import MAX_USAGE_CALL_ENTRIES, ModelCall, ToolCall
from corsair.settings import ModelSettings
from tests.unit.adk import ScriptedLlm, tool_batch_response
from tests.unit.test_agents import _audit_input, _producer_input, _proposal_args


def _metered(
    response: LlmResponse,
    *,
    prompt: int | None,
    output: int | None,
    cached: int | None = None,
    thoughts: int | None = None,
) -> LlmResponse:
    """Attach provider usage metadata the way ADK's model adapters report it."""

    response.usage_metadata = types.GenerateContentResponseUsageMetadata(
        prompt_token_count=prompt,
        candidates_token_count=output,
        cached_content_token_count=cached,
        thoughts_token_count=thoughts,
    )
    return response


def _text(text: str) -> LlmResponse:
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))


def _call(name: str, args: dict[str, Any]) -> LlmResponse:
    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part(function_call=types.FunctionCall(name=name, args=args))],
        )
    )


def _tool(name: str) -> BaseTool:
    return cast(BaseTool, SimpleNamespace(name=name))


def _tool_context(call_id: str) -> ToolContext:
    return cast(ToolContext, SimpleNamespace(function_call_id=call_id))


def _callback_context() -> CallbackContext:
    return cast(CallbackContext, object())


def _accounting(**limits: int) -> _EpisodeAccounting:
    return _EpisodeAccounting(
        max_llm_calls=limits.get("llm", 200),
        max_output_tokens=512,
        max_tool_calls=limits.get("tools", 200),
        role="producer",
    )


def test_saved_usage_without_telemetry_fields_still_decodes():
    usage = Usage.model_validate({"llm_calls": 2, "tool_calls": 1, "input_tokens": 9})

    assert usage.cached_input_tokens is None
    assert usage.thought_tokens is None
    assert usage.model_calls == []
    assert usage.tool_calls_detail == []
    assert usage.calls_truncated is False


def test_stored_producer_output_without_telemetry_still_decodes():
    stored = {"usage": {"llm_calls": 1, "tool_calls": 0, "seconds": 0.5}}

    assert ProducerOutput.model_validate(stored).usage.model_calls == []


def test_usage_call_lists_are_capped_by_the_contract():
    calls = [ModelCall(index=n, seconds=0.0) for n in range(1, MAX_USAGE_CALL_ENTRIES + 2)]

    with pytest.raises(ValidationError):
        Usage(llm_calls=len(calls), model_calls=calls)
    tools = [
        ToolCall(index=n, name="read_file", result_bytes=1, truncated=False, seconds=0.0)
        for n in range(1, MAX_USAGE_CALL_ENTRIES + 2)
    ]
    with pytest.raises(ValidationError):
        Usage(tool_calls=len(tools), tool_calls_detail=tools)


@pytest.mark.parametrize(
    "bad",
    [
        {"index": 0, "seconds": 0.0},
        {"index": 1, "seconds": -1.0},
        {"index": 1, "seconds": 0.0, "input_tokens": -1},
        {"index": 1, "seconds": 0.0, "cached_input_tokens": -1},
    ],
)
def test_model_call_rejects_impossible_values(bad: dict[str, Any]):
    with pytest.raises(ValidationError):
        ModelCall.model_validate(bad)


def test_tool_call_requires_a_named_tool_and_a_byte_count():
    with pytest.raises(ValidationError):
        ToolCall(index=1, name="", result_bytes=0, truncated=False, seconds=0.0)
    with pytest.raises(ValidationError):
        ToolCall(index=1, name="read_file", result_bytes=-1, truncated=False, seconds=0.0)


@pytest.mark.asyncio
async def test_scripted_producer_episode_records_each_model_and_tool_call(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    model = ScriptedLlm(
        model="scripted-telemetry",
        responses=[
            # The LiteLLM route reports an absent cache as 0: that is unknown, not zero.
            _metered(
                _call("read_file", {"path": "target.py"}),
                prompt=100,
                output=20,
                cached=0,
                thoughts=7,
            ),
            _metered(_text(json.dumps(_proposal_args())), prompt=150, output=30, cached=64),
        ],
    )

    output = await run_producer(_producer_input(store), ModelSettings(), store, model)

    assert output.feedback is None
    usage = output.usage
    assert (usage.llm_calls, usage.tool_calls) == (2, 1)
    assert (usage.input_tokens, usage.output_tokens) == (250, 50)
    assert usage.cached_input_tokens == 64
    assert usage.thought_tokens == 7
    assert usage.calls_truncated is False
    first, second = usage.model_calls
    assert (first.index, first.input_tokens, first.output_tokens) == (1, 100, 20)
    assert (first.cached_input_tokens, first.thought_tokens) == (None, 7)
    assert (second.index, second.input_tokens, second.output_tokens) == (2, 150, 30)
    assert (second.cached_input_tokens, second.thought_tokens) == (64, None)
    assert all(0 <= call.seconds <= usage.seconds for call in usage.model_calls)
    (read,) = usage.tool_calls_detail
    assert (read.index, read.name, read.truncated) == (1, "read_file", False)
    assert read.result_bytes > len("print")
    assert 0 <= read.seconds <= usage.seconds


@pytest.mark.asyncio
async def test_unreported_usage_stays_unknown_per_call_and_in_totals(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    model = ScriptedLlm(model="scripted-unmetered", responses=[_text(json.dumps(_proposal_args()))])

    output = await run_producer(_producer_input(store), ModelSettings(), store, model)

    usage = output.usage
    assert usage.input_tokens is None and usage.output_tokens is None
    assert usage.cached_input_tokens is None and usage.thought_tokens is None
    (call,) = usage.model_calls
    assert call.index == 1
    assert call.input_tokens is None and call.output_tokens is None
    assert call.cached_input_tokens is None and call.thought_tokens is None
    assert usage.tool_calls_detail == []


@pytest.mark.asyncio
async def test_auditor_episode_records_its_single_model_call(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    review = {"decision": "ACCEPT", "rule": "ALL", "reason": "grounded pair"}
    model = ScriptedLlm(
        model="scripted-audit-telemetry",
        responses=[_metered(_text(json.dumps(review)), prompt=80, output=12, thoughts=40)],
    )

    output = await run_auditor(_audit_input(store), ModelSettings(), model)

    assert output.feedback is None
    (call,) = output.usage.model_calls
    assert (call.input_tokens, call.output_tokens, call.thought_tokens) == (80, 12, 40)
    assert output.usage.thought_tokens == 40
    assert output.usage.tool_calls_detail == []


@pytest.mark.asyncio
async def test_a_tool_refused_by_the_budget_records_no_tool_entry(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    model = ScriptedLlm(
        model="scripted-tool-limit",
        responses=[tool_batch_response([("list_files", {}), ("read_file", {"path": "target.py"})])],
    )

    output = await run_producer(
        _producer_input(store, tool_call_limit=1), ModelSettings(), store, model
    )

    assert output.usage.tool_calls == 1
    (entry,) = output.usage.tool_calls_detail
    assert entry.index == 1
    assert entry.name in {"list_files", "read_file"}


@pytest.mark.asyncio
async def test_a_short_circuited_model_call_records_no_model_entry():
    accounting = _accounting(llm=1)
    context = cast(
        CallbackContext, SimpleNamespace(_invocation_context=SimpleNamespace(end_invocation=False))
    )

    assert await accounting.before_model(context, LlmRequest()) is None
    await accounting.after_model(context, _metered(_text("{}"), prompt=5, output=1))
    refused = await accounting.before_model(context, LlmRequest())

    assert refused is not None and accounting.llm_limit_exhausted
    assert [call.index for call in accounting.usage(1.0).model_calls] == [1]


@pytest.mark.asyncio
async def test_parallel_tool_calls_pair_by_function_call_id_and_keep_dispatch_order():
    accounting = _accounting()

    await accounting.before_tool(_tool("list_files"), {}, _tool_context("a"))
    await accounting.before_tool(_tool("read_file"), {}, _tool_context("b"))
    await accounting.after_tool(
        _tool("read_file"), {}, _tool_context("b"), {"path": "x.py", "content": "abc"}
    )
    await accounting.after_tool(
        _tool("list_files"), {}, _tool_context("a"), {"files": ["x.py"], "truncated": True}
    )

    first, second = accounting.usage(1.0).tool_calls_detail
    assert (first.index, first.name, first.truncated) == (1, "list_files", True)
    assert (second.index, second.name, second.truncated) == (2, "read_file", False)
    assert second.result_bytes == len(
        json.dumps(
            {"path": "x.py", "content": "abc"},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )


@pytest.mark.asyncio
async def test_after_tool_never_alters_the_tool_response():
    accounting = _accounting()
    await accounting.before_tool(_tool("read_file"), {}, _tool_context("a"))

    altered = await accounting.after_tool(
        _tool("read_file"), {}, _tool_context("a"), {"path": "x.py", "content": "abc"}
    )

    assert altered is None


@pytest.mark.asyncio
async def test_call_lists_stop_at_the_cap_while_totals_keep_counting():
    accounting = _accounting()
    calls = MAX_USAGE_CALL_ENTRIES + 6
    for n in range(calls):
        await accounting.before_model(_callback_context(), LlmRequest())
        await accounting.after_model(
            _callback_context(), _metered(_text("{}"), prompt=10, output=2, cached=3, thoughts=1)
        )
        await accounting.before_tool(_tool("read_file"), {}, _tool_context(f"call-{n}"))
        await accounting.after_tool(_tool("read_file"), {}, _tool_context(f"call-{n}"), {})

    usage = accounting.usage(1.0)

    assert usage.calls_truncated is True
    assert (usage.llm_calls, usage.tool_calls) == (calls, calls)
    assert len(usage.model_calls) == len(usage.tool_calls_detail) == MAX_USAGE_CALL_ENTRIES
    assert [call.index for call in usage.model_calls] == list(range(1, MAX_USAGE_CALL_ENTRIES + 1))
    assert (usage.input_tokens, usage.output_tokens) == (10 * calls, 2 * calls)
    assert (usage.cached_input_tokens, usage.thought_tokens) == (3 * calls, calls)


def test_an_untruncated_episode_does_not_claim_truncation():
    assert _accounting().usage(0.0).calls_truncated is False


@pytest.mark.asyncio
async def test_an_unknown_tool_name_is_counted_but_has_no_detail_entry(tmp_path: Path):
    """ADK answers an unknown tool without running it and skips after-tool callbacks."""

    store = ArtifactStore(tmp_path)
    model = ScriptedLlm(
        model="scripted-unknown-tool",
        structured_tools=False,
        responses=[
            _call("load_skill", {"name": "source-grounding"}),
            _call("set_model_response", _proposal_args()),
        ],
    )

    output = await run_producer(_producer_input(store), ModelSettings(), store, model)

    assert output.feedback is None and output.decision is not None
    assert output.usage.tool_calls == 2
    (entry,) = output.usage.tool_calls_detail
    assert (entry.index, entry.name) == (2, "set_model_response")
    assert output.usage.calls_truncated is False
