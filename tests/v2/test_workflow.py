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


async def _run(tmp_path, fakes, run_id, *, fixed=False, replace=(), progress=None):
    workflow.configure(fakes.stages(), models(), tmp_path / "matrix.yaml", progress)
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
    run = json.loads((run_dir / "run.json").read_text())
    assert (run["schema"], run["mode"], run["runtime_row"]) == ("corsair-v2-run/1", "temporal", "row")
    assert set(run["environments"]) == {"vulnerable", "fixed"} and run["finished_at"] is not None
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["rule_id"] == "R4" and summary["schema"] == "corsair-v2-run/1"
    assert set(summary["outcome"]["probes"]) == {"vulnerable", "fixed"}

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
    def setup():  # fresh outcome lists per run: the fake reads them in order
        return Fakes(rejections={"exploit": 1, "control": 2},
                     diagnose_outcomes={"exploit": ["errored", "ok", "errored"]})
    fakes = setup()
    verdict, run_dir = asyncio.run(_run(tmp_path, fakes, "durable-loop", fixed=True))
    direct = setup()
    record = RunRecorder.create(tmp_path, "direct-loop")
    expected = asyncio.run(run_case(case(tmp_path, True), stages=direct.stages(), models=models(),
                                    matrix_path=tmp_path / "matrix.yaml", record=record))
    assert verdict == expected and verdict.review_rounds == 3
    assert verdict.revisions == {"control": 2, "exploit": 1} and verdict.mechanical_fixes == {"exploit": 2}
    assert _steps(run_dir) == _steps(record.run_dir)
    assert {"probe.exploit.r1", "probe.exploit.r1.revision", "probe.control.r2", "review.3"} <= set(_steps(run_dir))
    assert fakes.names() == direct.names()
    feedback = [kw["review_feedback"] for _, kw in fakes.of("probe-exploit") if kw["review_feedback"]]
    assert len(feedback) == 1 and "exploit defect 0" in feedback[0]


def test_workflow_runs_the_same_second_attempt_as_direct_mode(tmp_path):
    def setup():  # attempt 1's PoV fails, attempt 2's is rejected once, revised and then passes (R4 on attempt 2)
        return Fakes(outcomes={("vulnerable", "exploit"): ["assertion_failed", "passed"],
                               ("fixed", "exploit"): ["assertion_failed", "assertion_failed"]},
                     review_invalid=[set(), {"exploit"}], real_decide=True)
    fakes = setup()
    verdict, run_dir = asyncio.run(_run(tmp_path, fakes, "durable-a2", fixed=True))
    direct = setup()
    record = RunRecorder.create(tmp_path, "direct-a2")
    expected = asyncio.run(run_case(case(tmp_path, True), stages=direct.stages(), models=models(),
                                    matrix_path=tmp_path / "matrix.yaml", record=record))
    assert verdict == expected
    assert (verdict.rule_id, verdict.attempt, verdict.fix) == ("R4", 2, "verified")
    assert [a.review_rounds for a in verdict.attempts] == [1, 2]
    assert _steps(run_dir) == _steps(record.run_dir)
    assert {"probe-exploit.a2", "review.a2.1", "probe.exploit.r1.a2", "review.a2.2", "execute-exploit-vulnerable.a2",
            "execute-exploit-fixed.a2"} <= set(_steps(run_dir))
    assert fakes.names() == direct.names()
    summary = json.loads((run_dir / "summary.json").read_text())
    assert [a["exploit_outcome"] for a in summary["attempts"]] == ["assertion_failed", "passed"]


@pytest.mark.parametrize("execution", ["activity", "worker"])
def test_progress_records_only_the_requested_run_not_client_or_worker_default(tmp_path, monkeypatch, execution):
    from temporalio.testing import ActivityEnvironment
    from corsair.v2.presentation import StageReporter

    client_record = RunRecorder.create(tmp_path / "client", "untouched")
    client_record.begin(case(tmp_path), mode="temporal")
    before = {p.relative_to(client_record.run_dir): p.read_bytes()
              for p in client_record.run_dir.rglob("*") if p.is_file()}
    worker_home = tmp_path / "worker-home"
    worker_home.mkdir()
    monkeypatch.chdir(worker_home)
    monkeypatch.setattr(workflow, "_CONFIG", None)  # restore the caller's configuration after this test
    observed = []
    started = RunRecorder.started

    def observe(recorder, step):
        observed.append((recorder.run_dir, step))
        started(recorder, step)

    monkeypatch.setattr(RunRecorder, "started", observe)
    requested = [tmp_path / "request-a", tmp_path / "request-b"]

    async def run(progress):
        for path in requested:
            if execution == "worker":
                await _run(tmp_path, Fakes(), path.name, progress=progress)
            else:
                workflow.configure(Fakes().stages(), models(), tmp_path / "matrix.yaml", progress)
                env = ActivityEnvironment()
                await env.run(workflow.begin_run, str(path), case(tmp_path))
                selected = await env.run(workflow.select, str(path), "select", case(tmp_path))
                await env.run(workflow.investigate, str(path), "investigate", case(tmp_path), selected.output)

    with StageReporter(color="never", animate=False) as progress:
        asyncio.run(run(progress))
    assert {path for path, _ in observed} == set(requested)
    assert all({"select", "investigate"} <= {step for run, step in observed if run == path} for path in requested)
    assert all(json.loads((path / "run.json").read_text())["last_started_step"] for path in requested)
    after = {p.relative_to(client_record.run_dir): p.read_bytes()
             for p in client_record.run_dir.rglob("*") if p.is_file()}
    assert after == before
    assert list(worker_home.iterdir()) == []  # no implicit .runs, client receipt or alternate run root
