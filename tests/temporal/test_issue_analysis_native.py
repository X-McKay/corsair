"""Same fixture agent in direct/durable modes, actual native activities and local spans."""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import logfire
import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from temporalio import workflow
from temporalio.api.enums.v1 import EventType
from temporalio.client import Client, WorkflowFailureError
from temporalio.exceptions import ApplicationError
from temporalio.worker import Replayer, Worker

with workflow.unsafe.imports_passed_through():
    from pydantic_ai import models
    from pydantic_ai.durable_exec.temporal import LogfirePlugin, PydanticAIPlugin
    from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded

    from corsair.workflows.issue_analysis import IssueAnalysisExecution, IssueAnalysisWorkflow
    from corsair.agents.issue_analysis import IssueAnalysisInput
    from tests.temporal.test_issue_analysis_support import AGENT, EXPECTED, MODELS, inputs


@workflow.defn
class FixtureIssueAnalysisWorkflow(IssueAnalysisWorkflow):
    __pydantic_ai_agents__ = [AGENT]
    model_keys = tuple(MODELS)

    @workflow.run
    async def run(self, inputs: IssueAnalysisInput, model_key: str,
                  request_limit: int = 3) -> IssueAnalysisExecution:
        return await super().run(inputs, model_key, request_limit)


def configure_local_spans():
    exporter = InMemorySpanExporter()
    logfire.configure(send_to_logfire=False, console=False, metrics=False,
                      additional_span_processors=[SimpleSpanProcessor(exporter)])
    return exporter


def write_spans(exporter, destination):
    # Native spans stay local; publish only identities/names and numeric usage.
    selected = {"gen_ai.operation.name", "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens",
                "gen_ai.tool.name", "temporalWorkflowID", "temporalRunID"}
    records = [{"name": span.name, "trace_id": f"{span.context.trace_id:032x}",
                "span_id": f"{span.context.span_id:016x}",
                "parent_span_id": f"{span.parent.span_id:016x}" if span.parent else None,
                "status": span.status.status_code.name,
                "exception_types": [event.attributes["exception.type"] for event in span.events
                                    if "exception.type" in event.attributes],
                "attributes": {key: value for key, value in span.attributes.items() if key in selected}}
               for span in exporter.get_finished_spans()]
    with Path(destination).open("x", encoding="utf-8") as output:
        json.dump(records, output, indent=2)


async def save_history(handle, destination):
    history = await handle.fetch_history()
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=True)
    with (root / f"{handle.id}.json").open("x", encoding="utf-8") as output:
        output.write(history.to_json())
    return history


@pytest.mark.parametrize("key", ["path_traversal", "missing_source", "instruction_injection"])
def test_issue_analysis_same_agent_direct_durable_replay_local_spans(temporal_address, request, key):
    async def check():
        exporter = configure_local_spans()
        plugins = [PydanticAIPlugin(), LogfirePlugin(metrics=False)]
        client = await Client.connect(temporal_address, plugins=plugins)
        identity = "corsair-analysis-" + str(uuid4())
        with models.override_allow_model_requests(False):
            direct = await FixtureIssueAnalysisWorkflow().run(inputs(key), key)
            direct_spans = exporter.get_finished_spans()
            assert sum(s.attributes.get("gen_ai.operation.name") == "chat"
                       for s in direct_spans) == direct.requests
            direct_tools = [s for s in direct_spans if s.attributes.get("gen_ai.operation.name") == "execute_tool"]
            assert sum(s.attributes.get("gen_ai.tool.name") == "read_source" for s in direct_tools) == direct.tool_calls
            assert sum(s.attributes.get("gen_ai.tool.name") == "final_result" for s in direct_tools) == 1
            assert len(direct_tools) == direct.tool_calls + 1
            async with Worker(client, task_queue=identity, workflows=[FixtureIssueAnalysisWorkflow]):
                handle = await client.start_workflow(FixtureIssueAnalysisWorkflow.run,
                                                    args=[inputs(key), key, 3], id=identity, task_queue=identity)
                durable = await asyncio.wait_for(handle.result(), 30)
        assert durable.output == direct.output == EXPECTED[key]
        assert (durable.requests, durable.tool_calls) == (direct.requests, direct.tool_calls)
        assert durable.requests in (1, 2) and durable.tool_calls in (0, 1)
        destination = request.config.getoption("--temporal-evidence-dir")
        history = await save_history(handle, destination)
        activities = [e.activity_task_scheduled_event_attributes.activity_type.name for e in history.events
                      if e.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED]
        assert sum(name.endswith("model_request") for name in activities) == durable.requests
        assert sum("call_tool" in name for name in activities) == durable.tool_calls
        assert all(e.activity_task_scheduled_event_attributes.retry_policy.maximum_attempts == 1
                   for e in history.events if e.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED)
        spans_before = exporter.get_finished_spans()
        durable_spans = spans_before[len(direct_spans):]
        workflow_traces = {s.context.trace_id for s in durable_spans
                           if s.attributes.get("temporalWorkflowID") == identity}
        model_spans = [s for s in durable_spans if s.attributes.get("gen_ai.operation.name") == "chat"]
        tool_spans = [s for s in durable_spans if s.attributes.get("gen_ai.operation.name") == "execute_tool"]
        assert len(model_spans) == durable.requests
        assert sum(s.attributes.get("gen_ai.tool.name") == "read_source" for s in tool_spans) == durable.tool_calls
        assert sum(s.attributes.get("gen_ai.tool.name") == "final_result" for s in tool_spans) == 1
        assert len(tool_spans) == durable.tool_calls + 1
        assert all(s.context.trace_id in workflow_traces for s in model_spans + tool_spans)
        assert any(s.name.startswith("RunWorkflow:") for s in durable_spans)
        assert sum(s.name.startswith("RunActivity:") for s in durable_spans) == len(activities)
        await Replayer(workflows=[FixtureIssueAnalysisWorkflow], plugins=plugins).replay_workflow(history)
        # A native history replay performs no model/tool requests or new execution spans.
        assert len(exporter.get_finished_spans()) == len(spans_before)
        write_spans(exporter, Path(destination) / f"{identity}-spans.json")
        with (Path(destination) / f"{identity}-comparison.json").open("x", encoding="utf-8") as output:
            json.dump({"case": key, "input_digest": inputs(key).input_digest,
                       "direct": {"requests": direct.requests, "tool_calls": direct.tool_calls,
                                  "input_tokens": direct.input_tokens, "output_tokens": direct.output_tokens},
                       "durable": {"requests": durable.requests, "tool_calls": durable.tool_calls,
                                   "input_tokens": durable.input_tokens, "output_tokens": durable.output_tokens},
                       "usage_source": "Fixture model estimates; no provider billing",
                       "native_activities": activities, "local_spans": len(spans_before),
                       "direct_spans": len(direct_spans), "durable_spans": len(durable_spans),
                       "durable_workflow_trace_ids": [f"{value:032x}" for value in workflow_traces]}, output, indent=2)
    asyncio.run(check())


@pytest.mark.parametrize("key,limit,exception_type", [
    ("unread", 3, UnexpectedModelBehavior), ("refused_path", 3, UnexpectedModelBehavior),
    ("path_traversal", 1, UsageLimitExceeded),
])
def test_issue_analysis_direct_durable_failure_preserves_native_cause(
    temporal_address, request, key, limit, exception_type,
):
    async def check():
        exporter = configure_local_spans()
        plugins = [PydanticAIPlugin(), LogfirePlugin(metrics=False)]
        client = await Client.connect(temporal_address, plugins=plugins)
        identity = "corsair-analysis-negative-" + str(uuid4())
        with models.override_allow_model_requests(False):
            with pytest.raises(exception_type):
                await FixtureIssueAnalysisWorkflow().run(inputs(), key, limit)
            direct_spans = exporter.get_finished_spans()
            assert sum(s.attributes.get("gen_ai.operation.name") == "chat" for s in direct_spans) == 1
            async with Worker(client, task_queue=identity, workflows=[FixtureIssueAnalysisWorkflow]):
                handle = await client.start_workflow(FixtureIssueAnalysisWorkflow.run,
                                                    args=[inputs(), key, limit], id=identity, task_queue=identity)
                with pytest.raises(WorkflowFailureError) as failure:
                    await asyncio.wait_for(handle.result(), 30)
        cause = failure.value.cause
        while cause is not None and not isinstance(cause, ApplicationError):
            cause = cause.cause
        assert isinstance(cause, ApplicationError)
        assert cause.type == exception_type.__name__
        destination = request.config.getoption("--temporal-evidence-dir")
        history = await save_history(handle, destination)
        assert history.events[-1].event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_FAILED
        assert all(e.activity_task_scheduled_event_attributes.retry_policy.maximum_attempts == 1
                   for e in history.events if e.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED)
        durable_spans = exporter.get_finished_spans()[len(direct_spans):]
        workflow_traces = {s.context.trace_id for s in durable_spans
                           if s.attributes.get("temporalWorkflowID") == identity}
        model_spans = [s for s in durable_spans if s.attributes.get("gen_ai.operation.name") == "chat"]
        assert len(model_spans) == 1 and model_spans[0].context.trace_id in workflow_traces
        assert any(s.status.status_code.name == "ERROR" for s in durable_spans)
        await Replayer(workflows=[FixtureIssueAnalysisWorkflow], plugins=plugins).replay_workflow(history)
        write_spans(exporter, Path(destination) / f"{identity}-spans.json")
    asyncio.run(check())
