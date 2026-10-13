"""Durable E2E-0 chain against direct mode on the reviewed SPEC-0018 pair, under an owned native service."""

import asyncio
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic_ai import models
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from temporalio.api.enums.v1 import EventType
from temporalio.client import Client, WorkflowFailureError
from temporalio.exceptions import ApplicationError
from temporalio.service import RPCError
from temporalio.worker import Replayer

from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.agents.issue_analysis.contracts import SourceFile
from corsair.composition.direct import CompositionBudget, SetupSource, StageModels, run_direct
from corsair.nodes.runtime.contracts import RuntimeInputs
from corsair.nodes.runtime.environment import RuntimeCatalog
from corsair.nodes.runtime.matrix import load
from corsair.workflows.chain import ACTIVITY_CONFIG, WORKFLOWS, ChainInvestigation, chain_worker, run_durable
from corsair.workflows.chain_runtime import STAGES, ChainRequest, StageKeys, configure_chain
from evals.fixture_e2e.case import (
    fixture_case, reviewed_runners, scripted_assessment, scripted_authoring, scripted_identification,
    scripted_planning,
)
from tests.agents.test_chain_environment_stage import (
    BASELINE, BUILD, OK, SETUP, Sandboxes, catalog, environment_model, pyproject, ready_draft,
)
from evals.fixture_e2e.reviewed import DISCOVER
from tests.temporal.support import EXECUTION_TIMEOUT, workflow_runner

PLUGINS = [PydanticAIPlugin()]


def abstaining_identification():
    async def respond(messages, info):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "status": "missing_information", "scope": "component", "target": None,
            "reason": "The configured documents directory is not in the saved source"})])
    return FunctionModel(respond)


def stages(**overrides):
    values = dict(identification=scripted_identification(), planning=scripted_planning(),
                  authoring=scripted_authoring(), assessment=scripted_assessment())
    return StageModels(**(values | overrides))


class Refusing:
    def run(self, *args, **kwargs):
        raise RuntimeError("candidate runner unavailable")


def runners_for(store, root, *, refuse=None):
    root.mkdir()
    reviewed = reviewed_runners(store, root)
    return lambda purpose: Refusing() if purpose == refuse else reviewed(purpose)


@pytest.fixture
def store(tmp_path):
    (tmp_path / "artifacts").mkdir(mode=0o700)
    with LocalArtifacts(tmp_path / "artifacts", max_bytes=1024 * 1024) as artifacts:
        yield artifacts


async def histories(client, identity, destination):
    """Parent and every started child; each is saved and replayed natively."""
    saved = []
    for workflow_id in (identity, *(f"{identity}/{stage}" for stage in STAGES)):
        handle = client.get_workflow_handle(workflow_id)
        try:
            history = await handle.fetch_history()
        except RPCError:
            continue  # A stage the chain never reached has no workflow.
        Path(destination).mkdir(parents=True, exist_ok=True)
        with (Path(destination) / f"{workflow_id.replace('/', '_')}.json").open("x", encoding="utf-8") as output:
            output.write(history.to_json())
        await Replayer(workflows=list(WORKFLOWS), plugins=PLUGINS,
                       workflow_runner=workflow_runner()).replay_workflow(history)
        saved.append((workflow_id, history))
    return saved


def scheduled(history):
    return [e for e in history.events if e.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED]


def slow_identification():
    async def respond(messages, info):
        await asyncio.sleep(3)
        return ModelResponse(parts=[ToolCallPart("read_source", {"path": "documents.py"})])
    return FunctionModel(respond)


async def both(temporal_address, store, tmp_path, models_, *, refuse=None, budget=CompositionBudget()):
    client = await Client.connect(temporal_address, plugins=PLUGINS)
    identity = "corsair-chain-" + str(uuid4())
    with models.override_allow_model_requests(False):
        direct = await run_direct(fixture_case(), models_, runners_for(store, tmp_path / "direct", refuse=refuse),
                                  budget)
        durable = await asyncio.wait_for(run_durable(
            fixture_case(), models_, runners_for(store, tmp_path / "durable", refuse=refuse), budget, client=client,
            workflow_id=identity, execution_timeout=EXECUTION_TIMEOUT, workflow_runner=workflow_runner()), 60)
    return client, identity, direct, durable


def same_routing(direct, durable):
    assert (durable.stopped_at, durable.reason) == (direct.stopped_at, direct.reason)
    assert [a.stage for a in durable.attempts] == [a.stage for a in direct.attempts]
    assert [a.failure is None for a in durable.attempts] == [a.failure is None for a in direct.attempts]
    assert durable.gate == direct.gate
    assert (durable.assessment and durable.assessment.admission) == (direct.assessment and direct.assessment.admission)
    assert [(e.revision, e.failure is None) for e in durable.executions] == [
        (e.revision, e.failure is None) for e in direct.executions]


def test_durable_chain_routes_the_true_pair_like_direct_mode(temporal_address, request, store, tmp_path):
    async def check():
        client, identity, direct, durable = await both(temporal_address, store, tmp_path, stages())
        same_routing(direct, durable)
        assert (durable.stopped_at, durable.reason) == (None, "complete")
        assert durable.assessment.admission.admitted and durable.gate.permitted == direct.gate.permitted
        assert (durable.identification, durable.plan, durable.observation_plan) == (
            direct.identification, direct.plan, direct.observation_plan)
        assert durable.patch.patch_sha256 == direct.patch.patch_sha256
        assert [a.usage.requests for a in durable.attempts] == [a.usage.requests for a in direct.attempts]
        assert [a.usage.tool_calls for a in durable.attempts] == [a.usage.tool_calls for a in direct.attempts]
        assert durable.limitations == direct.limitations
        for execution in durable.executions:
            assert execution.observed.operation == str(execution.operation)
            assert execution.observed.cleanup == "confirmed"
        saved = dict(await histories(client, identity, request.config.getoption("--temporal-evidence-dir")))
        assert set(saved) == {identity, *(f"{identity}/{stage}" for stage in STAGES)}
        revisions = scheduled(saved[identity])
        assert [e.activity_task_scheduled_event_attributes.activity_type.name for e in revisions] == [
            "corsair.chain.execute_revision"] * 2
        for workflow_id, history in saved.items():
            assert all(e.activity_task_scheduled_event_attributes.retry_policy.maximum_attempts == 1
                       for e in scheduled(history))
        children = [e for e in saved[identity].events
                    if e.event_type == EventType.EVENT_TYPE_START_CHILD_WORKFLOW_EXECUTION_INITIATED]
        timeouts = [e.start_child_workflow_execution_initiated_event_attributes.workflow_execution_timeout
                    .ToTimedelta().total_seconds() for e in children]
        budget = CompositionBudget()
        assert timeouts == [getattr(budget, stage).timeout_seconds for stage in STAGES]
        # Model requests and tool calls of the authoring child are native activities, run_tests included.
        authoring = [e.activity_task_scheduled_event_attributes.activity_type.name
                     for e in scheduled(saved[f"{identity}/authoring"])]
        assert sum(name.endswith("model_request") for name in authoring) == durable.attempts[2].usage.requests
        assert sum("call_tool" in name for name in authoring) == durable.attempts[2].usage.tool_calls == 4
    asyncio.run(check())


def test_identification_abstention_stops_both_modes_at_the_same_stage(temporal_address, request, store, tmp_path):
    async def check():
        client, identity, direct, durable = await both(
            temporal_address, store, tmp_path, stages(identification=abstaining_identification()))
        same_routing(direct, durable)
        assert durable.stopped_at == "identification" and "missing_information" in durable.reason
        assert durable.identification == direct.identification and durable.gate is None
        saved = dict(await histories(client, identity, request.config.getoption("--temporal-evidence-dir")))
        assert set(saved) == {identity, f"{identity}/identification"}
        assert not (tmp_path / "durable" / "development").exists()
    asyncio.run(check())


def test_a_raising_revision_activity_is_recorded_once_and_stops_at_execution(
    temporal_address, request, store, tmp_path,
):
    async def check():
        client, identity, direct, durable = await both(temporal_address, store, tmp_path, stages(),
                                                       refuse="candidate")
        same_routing(direct, durable)
        assert durable.stopped_at == "execution" and durable.gate is None
        assert durable.reason == "candidate run refused: candidate runner unavailable"
        candidate = durable.executions[1]
        assert (candidate.failure.kind, candidate.observed) == ("RuntimeError", None)
        saved = dict(await histories(client, identity, request.config.getoption("--temporal-evidence-dir")))
        parent = saved[identity].events
        assert len(scheduled(saved[identity])) == 2
        started = [e.activity_task_started_event_attributes.attempt for e in parent
                   if e.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_STARTED]
        failed = [e for e in parent if e.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_FAILED]
        assert started == [1, 1] and len(failed) == 1
        assert failed[0].activity_task_failed_event_attributes.failure.application_failure_info.type == "RuntimeError"
        assert parent[-1].event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED
    asyncio.run(check())


@pytest.mark.parametrize("keys,budget,kind", [
    (StageKeys("identification", "planning", "authoring", "unadmitted"), CompositionBudget(), "ModelKeyNotAdmitted"),
    (StageKeys(*STAGES), CompositionBudget(dev_runs=4), "BudgetNotAdmitted"),
])
def test_parent_admission_refusal_closes_before_any_child(temporal_address, request, store, tmp_path, keys, budget,
                                                         kind):
    async def check():
        client = await Client.connect(temporal_address, plugins=PLUGINS)
        identity = "corsair-chain-refused-" + str(uuid4())
        models_ = stages()
        configure_chain({stage: getattr(models_, stage) for stage in STAGES},
                        runners_for(store, tmp_path / "work"), activity_config=ACTIVITY_CONFIG)
        async with chain_worker(client, identity, workflow_runner=workflow_runner()):
            # The standalone worker holds its configuration: replacing it or a second worker is refused while it runs.
            with pytest.raises(RuntimeError):
                configure_chain({stage: getattr(models_, stage) for stage in STAGES},
                                runners_for(store, tmp_path / "other"), activity_config=ACTIVITY_CONFIG)
            with pytest.raises(RuntimeError):
                async with chain_worker(client, identity + "-second", workflow_runner=workflow_runner()):
                    pass
            handle = await client.start_workflow(ChainInvestigation.run, ChainRequest(fixture_case(), keys, budget),
                                                 id=identity, task_queue=identity, execution_timeout=EXECUTION_TIMEOUT)
            with pytest.raises(WorkflowFailureError) as failure:
                await asyncio.wait_for(handle.result(), 30)
        assert isinstance(failure.value.cause, ApplicationError)
        assert (failure.value.cause.type, failure.value.cause.non_retryable) == (kind, True)
        ((_, history),) = await histories(client, identity, request.config.getoption("--temporal-evidence-dir"))
        assert not any(e.event_type in (EventType.EVENT_TYPE_START_CHILD_WORKFLOW_EXECUTION_INITIATED,
                                        EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED,
                                        EventType.EVENT_TYPE_WORKFLOW_TASK_FAILED) for e in history.events)
    asyncio.run(check())


@pytest.mark.parametrize("limits,model,kind", [
    ({"request_limit": 1}, scripted_identification(), "UsageLimitExceeded"),
    ({"timeout_seconds": 1}, slow_identification(), "TimeoutError"),
])
def test_an_over_budget_or_timed_out_stage_closes_attributably(temporal_address, request, store, tmp_path, limits,
                                                               model, kind):
    async def check():
        budget = CompositionBudget(identification=CompositionBudget().identification.model_copy(update=limits))
        client, identity, direct, durable = await both(temporal_address, store, tmp_path,
                                                       stages(identification=model), budget=budget)
        assert durable.stopped_at == direct.stopped_at == "identification"
        # Both modes end on the same typed exhaustion of the cap derived from the stage input (SPEC-0043).
        limit = next(iter(limits))
        assert durable.reason == direct.reason
        assert durable.reason.startswith(f"identification budget exhausted: {limit} {limits[limit]} ")
        (attempt,) = durable.attempts
        assert attempt.failure.kind == kind and attempt.output is None
        assert attempt.exhausted == direct.attempts[0].exhausted and attempt.exhausted.limit == limit
        assert attempt.limits == direct.attempts[0].limits
        if kind == "UsageLimitExceeded":
            # Failed inside the child: same native exception, its usage and messages are kept.
            assert attempt.usage.requests == direct.attempts[0].usage.requests == 1
            assert len(attempt.messages) == len(direct.attempts[0].messages)
        else:
            # The child closed on its execution timeout without returning: usage is unknown, not zero.
            assert attempt.usage is None and attempt.messages == ()
        saved = dict(await histories(client, identity, request.config.getoption("--temporal-evidence-dir")))
        child = saved[f"{identity}/identification"].events[-1].event_type
        assert child == (EventType.EVENT_TYPE_WORKFLOW_EXECUTION_TIMED_OUT if kind == "TimeoutError"
                         else EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED)
    asyncio.run(check())


def test_chain_dataset_scores_the_durable_chain_like_direct_mode(temporal_address, request, tmp_path):
    from evals.fixture_chain.evaluate import dataset, evaluate, passed

    async def check():
        client = await Client.connect(temporal_address, plugins=PLUGINS)

        async def durable(case, stage_models, runners, budget):
            return await run_durable(case, stage_models, runners, budget, client=client,
                                     execution_timeout=EXECUTION_TIMEOUT)
        with models.override_allow_model_requests(False):
            return await evaluate(tmp_path / "evidence", mode="durable", run=durable)
    report = asyncio.run(check())
    assert len(report.cases) == len(dataset().cases) and passed(report)


@pytest.mark.parametrize("requires,prepared,status", [(">=3.8,<3.12", True, "unsupported"), (">=3.10", False, None)])
def test_runtime_stage_stops_both_modes_before_any_child(temporal_address, request, store, tmp_path, requires, prepared,
                                                         status):
    """SPEC-0060: one select_runtime activity, scheduled once; unsupported or no catalog ends the run there."""
    case = replace(fixture_case(), runtime=RuntimeInputs(files={
        "pyproject.toml": f'[project]\nrequires-python = "{requires}"\n[tool.pytest.ini_options]\n'.encode()}))
    catalog = RuntimeCatalog(load(), {"cpython-3.12-pytest": "corsair-python@sha256:" + "a" * 64}) if prepared else None

    async def check():
        client = await Client.connect(temporal_address, plugins=PLUGINS)
        identity = "corsair-chain-runtime-" + str(uuid4())
        with models.override_allow_model_requests(False):
            direct = await run_direct(case, stages(), runners_for(store, tmp_path / "direct"), catalog=catalog)
            durable = await asyncio.wait_for(run_durable(
                case, stages(), runners_for(store, tmp_path / "durable"), client=client, catalog=catalog,
                workflow_id=identity, execution_timeout=EXECUTION_TIMEOUT, workflow_runner=workflow_runner()), 60)
        same_routing(direct, durable)
        assert durable.stopped_at == "runtime" and durable.attempts == () and durable.runtime == direct.runtime
        if status:
            assert durable.runtime.status == status and durable.reason == direct.reason
        else:
            assert durable.runtime is None
            assert durable.reason.startswith("runtime selection failed: RuntimeCatalogMissing: The case carries")
        saved = dict(await histories(client, identity, request.config.getoption("--temporal-evidence-dir")))
        assert set(saved) == {identity}
        selections = scheduled(saved[identity])
        assert [e.activity_task_scheduled_event_attributes.activity_type.name for e in selections] == [
            "corsair.chain.select_runtime"]
        assert selections[0].activity_task_scheduled_event_attributes.retry_policy.maximum_attempts == 1
        assert not (tmp_path / "durable" / "development").exists()
    asyncio.run(check())


ENVIRONMENT_CASES = {
    "ready": (OK, [BUILD, DISCOVER, BASELINE], ready_draft()),
    "blocked": (OK | {DISCOVER: (2, "ERROR: file or directory not found: tests\n")}, [BUILD, DISCOVER],
                {"status": "blocked", "layer": "discovery", "evidence": "file or directory not found", "run_ids": [2],
                 "citations": []}),
}


def without_operations(result):
    dumped = result.model_dump(mode="json")
    return dumped | {"receipts": [r | {"operation": None} for r in dumped["receipts"]]}


@pytest.mark.parametrize("outcome", sorted(ENVIRONMENT_CASES))
def test_durable_environment_stage_matches_direct_mode(temporal_address, request, store, tmp_path, outcome):
    """PLAN-0075: the whole environment stage is one activity, scheduled once, and routes like direct mode."""
    observations, commands, draft = ENVIRONMENT_CASES[outcome]
    case = replace(fixture_case(), runtime=pyproject(">=3.10"), setup=SETUP)

    async def check():
        client = await Client.connect(temporal_address, plugins=PLUGINS)
        identity = "corsair-chain-environment-" + str(uuid4())
        direct_sandboxes, durable_sandboxes = Sandboxes(observations), Sandboxes(observations)
        with models.override_allow_model_requests(False):
            direct = await run_direct(case, stages(environment=environment_model(commands, draft)),
                                      runners_for(store, tmp_path / "direct"), catalog=catalog(),
                                      preparation=direct_sandboxes)
            durable = await asyncio.wait_for(run_durable(
                case, stages(environment=environment_model(commands, draft)), runners_for(store, tmp_path / "durable"),
                client=client, catalog=catalog(), preparation=durable_sandboxes, workflow_id=identity,
                execution_timeout=EXECUTION_TIMEOUT, workflow_runner=workflow_runner()), 60)
        same_routing(direct, durable)
        # Equal but for each setup command's operation id, which is random in both modes.
        assert without_operations(durable.environment) == without_operations(direct.environment)
        assert durable.environment.status == outcome
        assert durable.limitations == direct.limitations and durable.runtime == direct.runtime
        assert durable.attempts[0].cleanup == direct.attempts[0].cleanup == "confirmed"
        assert durable_sandboxes.commands == direct_sandboxes.commands == list(commands)
        assert len(durable_sandboxes.prepared) == len(durable_sandboxes.released) == 1
        saved = dict(await histories(client, identity, request.config.getoption("--temporal-evidence-dir")))
        names = [e.activity_task_scheduled_event_attributes.activity_type.name for e in scheduled(saved[identity])]
        assert names[:2] == ["corsair.chain.select_runtime", "corsair.chain.prepare_environment"]
        assert names.count("corsair.chain.prepare_environment") == 1
        environment = scheduled(saved[identity])[1].activity_task_scheduled_event_attributes
        assert environment.retry_policy.maximum_attempts == 1
        if outcome == "blocked":
            assert set(saved) == {identity} and durable.stopped_at == "environment"
    asyncio.run(check())


@pytest.mark.parametrize("environment, preparation", [(False, True), (True, False)])
def test_durable_environment_stage_without_its_ports_stops_like_direct_mode(temporal_address, request, store,
                                                                           tmp_path, environment, preparation):
    """SPEC-0068: no environment model key or no worker preparation stops with PreparationMissing, never the declaration."""
    case = replace(fixture_case(), runtime=pyproject(">=3.10"), setup=SETUP)
    model = environment_model([], ready_draft()) if environment else None
    sandboxes = Sandboxes(OK) if preparation else None

    async def check():
        client = await Client.connect(temporal_address, plugins=PLUGINS)
        identity = "corsair-chain-environment-" + str(uuid4())
        with models.override_allow_model_requests(False):
            direct = await run_direct(case, stages(environment=model), runners_for(store, tmp_path / "direct"),
                                      catalog=catalog(), preparation=sandboxes)
            durable = await asyncio.wait_for(run_durable(
                case, stages(environment=model), runners_for(store, tmp_path / "durable"), client=client,
                catalog=catalog(), preparation=sandboxes, workflow_id=identity, execution_timeout=EXECUTION_TIMEOUT,
                workflow_runner=workflow_runner()), 60)
        same_routing(direct, durable)
        assert durable.reason.startswith("environment produced no output: PreparationMissing: ")
        # Review of #103: no sandbox was ever made, so cleanup is not "unconfirmed" in either mode.
        assert durable.attempts[0].cleanup is direct.attempts[0].cleanup is None
        assert durable.limitations == direct.limitations
        saved = dict(await histories(client, identity, request.config.getoption("--temporal-evidence-dir")))
        names = [e.activity_task_scheduled_event_attributes.activity_type.name for e in scheduled(saved[identity])]
        assert names == ["corsair.chain.select_runtime"] + (["corsair.chain.prepare_environment"] if environment else [])
    asyncio.run(check())
