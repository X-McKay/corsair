"""Durable-chain payloads, admission and worker-side runner resolution without a Temporal service."""

import asyncio
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic_ai import models
from pydantic_ai.durable_exec.temporal import PydanticAIPayloadConverter
from pydantic_ai.exceptions import UserError
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelRequest, UserPromptPart
from temporalio.common import RetryPolicy
from temporalio.converter import DataConverter
from temporalio.exceptions import ActivityError, ApplicationError, RetryState

from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.agents.evidence_assessment.contracts import EvidenceAssessment
from corsair.agents.issue_analysis.identification_contracts import IssueIdentification
from corsair.agents.test_authoring.contracts import AuthoringResult, TestAuthoringInput, TestPatch
from corsair.agents.test_authoring.tools import AuthoringBudget, AuthoringDependencies
from corsair.agents.test_planning.contracts import TestPlan
from corsair.composition.direct import CompositionBudget, RecordedFailure, StageModels, run_direct
from corsair.composition.evidence import freeze
from corsair.nodes.runtime.contracts import RuntimeInputs, RuntimeOutcome
from corsair.nodes.runtime.environment import RuntimeCatalog
from corsair.nodes.runtime.matrix import load
from corsair.ports.test_runner import ApprovedPatch, PatchFile
from corsair.workflows.chain import _admit, run_durable
from corsair.workflows.chain_runtime import (
    AuthoringPayload, AuthoringRunContext, ChainRequest, ChainResult, RevisionRequest, StageKeys, StageRecord,
    WorkerRunner, chain_result, configure_chain, failure_record, select_runtime, serving, within,
)
from evals.fixture_e2e.case import (
    fixture_case, reviewed_runners, scripted_assessment, scripted_authoring, scripted_identification,
    scripted_planning,
)

ACTIVITY_CONFIG = {"start_to_close_timeout": timedelta(seconds=10), "retry_policy": RetryPolicy(maximum_attempts=1)}
CONVERTER = DataConverter(payload_converter_class=PydanticAIPayloadConverter)


def stage_models():
    return StageModels(identification=scripted_identification(), planning=scripted_planning(),
                       authoring=scripted_authoring(), assessment=scripted_assessment())


def canonical(value):
    """Tool return contents are untyped (``Any``), so messages compare in their native JSON form."""
    if isinstance(value, ChainResult):
        return replace(value, attempts=tuple(canonical(a) for a in value.attempts))
    return replace(value, messages=ModelMessagesTypeAdapter.dump_json(list(value.messages)))


async def roundtrip(value, type_hint):
    (restored,) = await CONVERTER.decode(await CONVERTER.encode([value]), [type_hint])
    return restored


@pytest.fixture
def direct(tmp_path):
    (tmp_path / "artifacts").mkdir(mode=0o700)
    (tmp_path / "work").mkdir()
    with LocalArtifacts(tmp_path / "artifacts", max_bytes=1024 * 1024) as store, \
            models.override_allow_model_requests(False):
        yield asyncio.run(run_direct(fixture_case(), stage_models(), reviewed_runners(store, tmp_path / "work")))


def test_direct_run_records_and_stage_payloads_roundtrip(direct):
    async def check():
        result = chain_result(direct)
        assert canonical(await roundtrip(result, ChainResult)) == canonical(result)
        assert [type(a.output) for a in result.attempts] == [IssueIdentification, type(direct.plan), TestPatch,
                                                              EvidenceAssessment]
        for attempt, hint in zip(direct.attempts, (IssueIdentification, TestPlan, AuthoringResult, EvidenceAssessment)):
            record = StageRecord(attempt.output, attempt.usage, attempt.messages, None)
            assert canonical(await roundtrip(record, StageRecord[hint])) == canonical(record)
        request = ChainRequest(fixture_case(), StageKeys("a", "b", "c", "d"), CompositionBudget())
        assert await roundtrip(request, ChainRequest) == request
    asyncio.run(check())


def test_revision_payloads_keep_non_utf8_bytes(direct):
    async def check():
        patch = freeze(direct.patch, ("test_documents.py",))
        request = RevisionRequest(revision="candidate", patch=patch, control_test_id="a.py::t", security_test_id="a.py::u",
                                  discovery_command=("python",), operation=uuid4())
        assert await roundtrip(request, RevisionRequest) == request
        raw = ApprovedPatch((PatchFile("test_x.py", b"\xff\x00"),), ("test_x.py",))
        assert (await roundtrip(request.model_copy(update={"patch": raw}), RevisionRequest)).patch == raw
    asyncio.run(check())


def test_runtime_stage_payloads_and_worker_activity(tmp_path):
    """SPEC-0060: build-file bytes and the outcome cross the payload boundary; the worker's catalog answers."""
    inputs = RuntimeInputs(files={"pyproject.toml": b'[project]\nrequires-python = ">=3.10"\n[tool.pytest.ini_options]\n',
                                  "documents.py": b"\xff\x00"})
    catalog = RuntimeCatalog(load(), {"cpython-3.12-pytest": "corsair-python@sha256:" + "a" * 64})

    async def check():
        request = ChainRequest(replace(fixture_case(), runtime=inputs), StageKeys("a", "b", "c", "d"), CompositionBudget())
        assert await roundtrip(request, ChainRequest) == request
        configure_chain({"scripted": scripted_identification()}, reviewed_runners(None, tmp_path),
                        activity_config=ACTIVITY_CONFIG)
        with pytest.raises(ApplicationError) as missing:
            await select_runtime(inputs)
        assert (missing.value.type, missing.value.non_retryable) == ("RuntimeCatalogMissing", True)
        configure_chain({"scripted": scripted_identification()}, reviewed_runners(None, tmp_path),
                        activity_config=ACTIVITY_CONFIG, catalog=catalog)
        outcome = await select_runtime(inputs)
        assert (outcome.status, outcome.image) == ("supported", catalog.prepared["cpython-3.12-pytest"])
        assert await roundtrip(outcome, RuntimeOutcome) == outcome
        result = ChainResult(stopped_at="runtime", reason=outcome.reason, attempts=(), runtime=outcome)
        assert await roundtrip(result, ChainResult) == result
    asyncio.run(check())


def test_failure_records_keep_the_native_cause():
    cause = ApplicationError("runner refused", type="RuntimeError")
    wrapped = ActivityError("Activity task failed", scheduled_event_id=1, started_event_id=2, identity="w",
                            activity_type="a", activity_id="1", retry_state=RetryState.MAXIMUM_ATTEMPTS_REACHED)
    wrapped.__cause__ = cause
    assert (failure_record(wrapped).kind, failure_record(wrapped).message) == ("RuntimeError", "runner refused")
    assert failure_record(RecordedFailure("TimeoutError", "late")).kind == "TimeoutError"
    assert failure_record(ValueError("bad")).kind == "ValueError"


def test_admission_refuses_unconfigured_keys_and_budgets_before_any_request(tmp_path):
    ceiling = CompositionBudget()
    configure_chain({"scripted": scripted_identification()}, reviewed_runners(None, tmp_path),
                    activity_config=ACTIVITY_CONFIG, ceiling=ceiling)
    assert _admit(("scripted",), ceiling).model_keys == {"scripted"}
    over = ceiling.model_copy(update={"planning": ceiling.planning.model_copy(update={"request_limit": ceiling.planning.request_limit + 1})})
    cases = [(("other",), ceiling, "ModelKeyNotAdmitted"), (("scripted",), over, "BudgetNotAdmitted"),
             (("scripted",), ceiling.model_copy(update={"dev_runs": 4}), "BudgetNotAdmitted"),
             (("scripted",), ceiling.model_copy(update={"output_retries": 0}), "BudgetNotAdmitted"),
             (("scripted",), ceiling.model_copy(update={"admission_refusals": 2}), "BudgetNotAdmitted"),
             # Codex review on 78f1690: the derivation terms are operator-owned like the caps.
             *((("scripted",), ceiling.model_copy(update={"authoring": ceiling.authoring.model_copy(
                 update={term: getattr(ceiling.authoring, term) + 1})}), "BudgetNotAdmitted")
               for term in ("slack_tool_calls", "tokens_per_request"))]
    for keys, budget, kind in cases:
        with pytest.raises(ApplicationError) as refusal:
            _admit(keys, budget)
        assert (refusal.value.type, refusal.value.non_retryable) == (kind, True)
    assert within(ceiling.model_copy(update={"dev_runs": 1}), ceiling)
    with pytest.raises(ValueError):
        configure_chain({"default": scripted_identification()}, reviewed_runners(None, tmp_path),
                        activity_config=ACTIVITY_CONFIG)


def test_a_serving_configuration_refuses_replacement_and_overlapping_durable_runs(tmp_path):
    runners = reviewed_runners(None, tmp_path)
    configure_chain({"scripted": scripted_identification()}, runners, activity_config=ACTIVITY_CONFIG)
    with serving():
        with pytest.raises(RuntimeError):
            configure_chain({"scripted": scripted_identification()}, runners, activity_config=ACTIVITY_CONFIG)
        with pytest.raises(RuntimeError):
            # Refused before any client call, so a second run never resolves through the first run's agents.
            asyncio.run(run_durable(fixture_case(), stage_models(), runners, client=None))
        with pytest.raises(RuntimeError), serving():
            pass
    configure_chain({"scripted": scripted_identification()}, runners, activity_config=ACTIVITY_CONFIG)


def test_authoring_context_resolves_the_runner_on_the_worker_and_carries_messages(direct):
    resolved = []

    def runners(purpose):
        resolved.append(purpose)
        return object()
    configure_chain({"scripted": scripted_authoring()}, runners, activity_config=ACTIVITY_CONFIG)
    case = fixture_case()
    payload = AuthoringPayload(TestAuthoringInput(plan=direct.plan, source_files=case.issue.source_files,
                                                  environment=case.environment),
                               WorkerRunner("development"), AuthoringBudget(dev_runs=2))
    messages = [ModelRequest(parts=[UserPromptPart("written")])]
    # As an activity receives it: plain JSON values, rehydrated into native messages.
    serialized = {"run_id": "r", "messages": ModelMessagesTypeAdapter.dump_python(messages, mode="json")}
    ctx = AuthoringRunContext.deserialize_run_context(serialized, deps=payload)
    assert isinstance(ctx.deps, AuthoringDependencies) and ctx.deps.budget.dev_runs == 2 and resolved == ["development"]
    assert ctx.messages == messages
    with pytest.raises(UserError):
        AuthoringRunContext.deserialize_run_context(serialized, deps=AuthoringPayload(
            payload.inputs, WorkerRunner("candidate"), payload.budget))
    with pytest.raises(RuntimeError):
        WorkerRunner("development").run()
