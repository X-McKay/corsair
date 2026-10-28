"""Native ADK schemas and outcome-blind packets for recipe-free roles."""

import json

import pytest

from corsair.adapters.inference.execution import run_execution_auditor, run_execution_producer
from corsair.agents.auditor.execution import build_execution_auditor
from corsair.agents.producer.execution import build_execution_producer
from corsair.contracts.execution import (
    PlanAudit,
)
from corsair.contracts.execution import (
    TestPlan as Plan,
)
from corsair.settings import Settings
from tests.unit.adk import ScriptedLlm, text_response
from tests.unit.execution import Reader, round_input


def test_factories_declare_canonical_schemas():
    assert build_execution_producer("model", Reader()).output_schema is Plan
    assert build_execution_auditor("model").output_schema is PlanAudit
    assert build_execution_auditor("model").tools == []


@pytest.mark.asyncio
async def test_native_producer_and_auditor_are_independent():
    item = round_input()
    plan = Plan(
        hypothesis="Call answer",
        revision=1,
        locations=[{"path": "reader.py"}],
        commands=[{"argv": ["python", "-c", "print(1)"]}],
    )
    producer = ScriptedLlm(model="producer-test", responses=[text_response(plan.model_dump_json())])
    output = await run_execution_producer(item, Settings(), Reader(), producer)
    assert output.plan == plan and output.error is None
    auditor = ScriptedLlm(
        model="auditor-test",
        responses=[text_response(json.dumps({"decision": "accepted", "reasons": []}))],
    )
    reviewed = await run_execution_auditor(item, plan, Settings(), Reader(), auditor)
    assert reviewed.audit == PlanAudit(decision="accepted")
    assert output.source_paths == ["reader.py"]


@pytest.mark.asyncio
async def test_unread_source_is_rejected():
    plan = Plan(
        hypothesis="Unrelated",
        revision=1,
        locations=[{"path": "unread.py"}],
        commands=[{"argv": ["true"]}],
    )
    model = ScriptedLlm(model="unread", responses=[text_response(plan.model_dump_json())])
    result = await run_execution_producer(round_input(), Settings(), Reader(), model)
    assert result.error == "SOURCE_UNGROUNDED" and result.plan is None


@pytest.mark.asyncio
async def test_invalid_native_schema_has_categorical_diagnostics():
    model = ScriptedLlm(model="invalid-v3", responses=[text_response('{"revision":"wrong"}')])
    output = await run_execution_producer(round_input(), Settings(), Reader(), model)
    assert output.error == "OUTPUT_INVALID"
    assert output.completion_errors.get("missing", 0) > 0
