"""The durable workflow runs the same routing on three queues, end to end with fake stages on a test server."""
import asyncio
import json
from contextlib import AsyncExitStack

import pytest
from temporalio import activity
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ApplicationError
from temporalio.worker import Worker

from chain_fakes import Fakes, case, models
from corsair.v2 import workflow
from corsair.v2.chain import run_case
from corsair.v2.record import RunRecorder


async def _environment():
    from temporalio.testing import WorkflowEnvironment
    try:
        return await WorkflowEnvironment.start_time_skipping(data_converter=pydantic_data_converter)
    except Exception as exc:  # no cached test server and no network: skip, never fail CI
        pytest.skip(f"Temporal test server unavailable: {exc}")


async def _run(tmp_path, fakes, run_id, *, fixed=False, replace=()):
    workflow.configure(fakes.stages(), models(), tmp_path / "matrix.yaml")
    run_dir = tmp_path / run_id
    async with await _environment() as env, AsyncExitStack() as stack:
        built = workflow.workers(env.client, workspace_slots=2,
                                 queues=tuple(q for q in (workflow.MODEL_QUEUE, workflow.WORKSPACE_QUEUE,
                                                          workflow.CONTROL_QUEUE) if q not in dict(replace)))
        built += [Worker(env.client, task_queue=queue, activities=activities) for queue, activities in replace]
        for worker in built:
            await stack.enter_async_context(worker)
        request = workflow.RunRequest(case=case(tmp_path, fixed), run_dir=str(run_dir))
        verdict = await workflow.run_workflow(env.client, request, workflow_id=f"wf-{run_id}")
    return verdict, run_dir


def _steps(run_dir):
    return [t["step"] for t in json.loads((run_dir / "timings.json").read_text())]


def test_workflow_runs_the_same_chain_as_direct_mode(tmp_path):
    fakes = Fakes(diagnose_outcomes={"exploit": "errored"})
    verdict, run_dir = asyncio.run(_run(tmp_path, fakes, "durable", fixed=True))
    assert (verdict.label.value, verdict.rule_id, verdict.terminal_reason.value) == ("LIKELY_EXPLOITABLE", "R4", "ok")
    assert len(verdict.runs) == 4
    assert json.loads((run_dir / "run.json").read_text())["mode"] == "temporal"
    assert json.loads((run_dir / "summary.json").read_text())["rule_id"] == "R4"

    direct = Fakes(diagnose_outcomes={"exploit": "errored"})
    record = RunRecorder.create(tmp_path, "direct")
    expected = asyncio.run(run_case(case(tmp_path, True), stages=direct.stages(), models=models(),
                                    matrix_path=tmp_path / "matrix.yaml", record=record))
    assert _steps(run_dir) == _steps(record.run_dir)
    assert verdict == expected
    assert fakes.names() == direct.names()
    assert [kw["runtime"] for _, kw in fakes.of("review")] == [kw["runtime"] for _, kw in direct.of("review")]
    assert all(kw["runtime"] is not None for _, kw in fakes.of("review"))


def test_container_activity_failure_runs_once_and_is_infra(tmp_path):
    attempts = []

    @activity.defn(name="corsair.v2.execute")
    async def lost(*args) -> None:
        attempts.append(args[1])
        raise ApplicationError("container vanished mid-run")

    replacement = (workflow.WORKSPACE_QUEUE, [workflow.replay, workflow.diagnose, lost])
    verdict, run_dir = asyncio.run(_run(tmp_path, Fakes(), "lost", replace=(replacement,)))
    assert attempts == ["execute-control-vulnerable"]  # exactly once, never retried
    assert verdict.terminal_reason.value == "infra_error"
    note = json.loads((run_dir / "stages" / "execute-control-vulnerable.activity-failure.json").read_text())
    assert "container vanished" in note["error"]


def test_queue_layout_and_slots():
    async def configs():
        async with await _environment() as env:
            return {w.task_queue: w.config() for w in workflow.workers(env.client, workspace_slots=7)}
    built = asyncio.run(configs())
    assert set(built) == {"corsair-v2-model", "corsair-v2-workspace", "corsair-v2-control"}
    assert built["corsair-v2-model"]["max_concurrent_activities"] == 1
    assert built["corsair-v2-workspace"]["max_concurrent_activities"] == 7
    assert built["corsair-v2-control"]["workflows"] == [workflow.InvestigationWorkflow]
    assert {a.__name__ for a in built["corsair-v2-workspace"]["activities"]} == {"replay", "diagnose", "execute"}


def test_workflow_runs_the_same_review_loop_as_direct_mode(tmp_path):
    setup = dict(rejections={"exploit": 1, "control": 2}, diagnose_outcomes={"exploit": "errored"})
    fakes = Fakes(**setup)
    verdict, run_dir = asyncio.run(_run(tmp_path, fakes, "durable-loop", fixed=True))
    direct = Fakes(**setup)
    record = RunRecorder.create(tmp_path, "direct-loop")
    expected = asyncio.run(run_case(case(tmp_path, True), stages=direct.stages(), models=models(),
                                    matrix_path=tmp_path / "matrix.yaml", record=record))
    assert verdict == expected and verdict.review_rounds == 3
    assert verdict.revisions == {"control": 2, "exploit": 1}
    assert _steps(run_dir) == _steps(record.run_dir)
    assert {"probe.exploit.r1", "probe.exploit.r1.revision", "probe.control.r2", "review.3"} <= set(_steps(run_dir))
    assert fakes.names() == direct.names()
    feedback = [kw["review_feedback"] for _, kw in fakes.of("probe-exploit") if kw["review_feedback"]]
    assert len(feedback) == 1 and "exploit defect 0" in feedback[0]
