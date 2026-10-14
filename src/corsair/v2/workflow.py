"""Durable mode: one Temporal workflow per case, running the same routing and stage functions as direct mode.

``InvestigationWorkflow`` runs ``chain.compose`` unchanged (the review loop included); each step is one activity whose body is
``chain.LocalOps`` on the worker, so stage calls, wall-time measurement, recording and error mapping are the code
direct mode runs. Three task queues:

- ``corsair-v2-model``: every agent step (one slot on its worker, so one model episode at a time across all runs).
- ``corsair-v2-workspace``: container work (replay, diagnose, execute); slots sized to the Docker host.
- ``corsair-v2-control``: the workflow itself, select, decide and the run-record bookends.

Durability granularity: each agent stage is ONE activity, not native ``TemporalDurability`` per model request. The
stage functions build their agent inside the call from a ``Model`` argument, while ``TemporalDurability`` needs
every agent and model registered on the worker before it starts; wrapping whole stages is the simple correct fit.
The consequence is that a retried agent activity re-runs its whole episode.

Retry classes:

- Agent steps: up to 3 attempts with a finite start-to-close timeout. Provider errors are caught inside the step
  and returned as ``provider_error`` (nothing retried blindly); only activity-level failures such as a lost worker
  or a timeout are retried. The Builder step runs shell commands, so it runs exactly once.
- Reads (select) and pure code (decide, record bookends): up to 3 attempts.
- Container work (replay, diagnose, execute): exactly once (``maximum_attempts=1``). An activity that fails or times
  out is an uncertain outcome and is recorded as ``infra_error``. Container create and remove retries, bounded and
  against the same labelled identity, belong to the workspace backend inside the activity.

Workers on different hosts must share the run directory's filesystem: activities write the run record there.
"""
from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict
from temporalio import activity, workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from pydantic_ai.models import Model

    from .chain import Budget, Diagnosis, LocalOps, Progress, Replayed, Stages, StepResult, compose
    from .contracts import (BuildResult, Case, Environment, FrozenPatch, ProbeBrief, ProbeDraft, ProbePlan, ProbeRun,
                            Recipe, Runtime, TerminalReason, Validity, Verdict)
    from .record import RunRecorder

MODEL_QUEUE = "corsair-v2-model"
WORKSPACE_QUEUE = "corsair-v2-workspace"
CONTROL_QUEUE = "corsair-v2-control"

AGENT_TIMEOUT = timedelta(hours=1)
BUILD_TIMEOUT = timedelta(hours=2)
CONTAINER_TIMEOUT = timedelta(hours=1)
CONTROL_TIMEOUT = timedelta(minutes=2)

MODEL_RETRY = RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=5))
READ_RETRY = RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=1))
ONCE = RetryPolicy(maximum_attempts=1)


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    case: Case
    run_dir: str
    budget: Budget = Budget()
    grounding: bool = False


# --- Worker configuration -----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkerConfig:
    stages: Stages
    models: Mapping[str, Model]
    matrix_path: Path
    progress: Progress | None = None
    provider_config: Path | None = None  # the file the models were built from; only its digest is recorded


_CONFIG: WorkerConfig | None = None


def configure(stages: Stages, models: Mapping[str, Model], matrix_path: Path, progress: Progress | None = None,
              provider_config: Path | None = None) -> None:
    """Bind this worker process's stages, models and matrix; activities read it. One configuration per process."""
    global _CONFIG
    _CONFIG = WorkerConfig(stages, models, Path(matrix_path), progress,
                           Path(provider_config) if provider_config is not None else None)


def _ops(run_dir: str) -> LocalOps:
    if _CONFIG is None:
        raise RuntimeError("corsair.v2.workflow.configure must run before a worker serves activities")
    return LocalOps(_CONFIG.stages, _CONFIG.models, _CONFIG.matrix_path, RunRecorder(Path(run_dir)),
                    _CONFIG.progress)


# --- Activities (names are replay contracts) ----------------------------------------------------------------------


@activity.defn(name="corsair.v2.begin_run")
async def begin_run(run_dir: str, case: Case) -> None:
    config = _CONFIG  # a control worker without a configuration records the digests as unknown
    RunRecorder(Path(run_dir)).begin(case, mode="temporal",
                                     provider_config=config.provider_config if config else None,
                                     matrix=config.matrix_path if config else None)


@activity.defn(name="corsair.v2.finish_run")
async def finish_run(run_dir: str, verdict: Verdict) -> None:
    RunRecorder(Path(run_dir)).finish(verdict)


@activity.defn(name="corsair.v2.note_failure")
async def note_failure(run_dir: str, step: str, detail: str) -> None:
    RunRecorder(Path(run_dir)).stage(f"{step}.activity-failure", inputs={}, output=None, wall_s=None, error=detail)


@activity.defn(name="corsair.v2.ground")
async def ground(run_dir: str, step: str, case: Case) -> StepResult[None]:
    return await _ops(run_dir).ground(step, case)


@activity.defn(name="corsair.v2.select")
async def select(run_dir: str, step: str, case: Case) -> StepResult[Runtime]:
    return await _ops(run_dir).select(step, case)


@activity.defn(name="corsair.v2.investigate")
async def investigate(run_dir: str, step: str, case: Case, runtime: Runtime) -> StepResult[ProbePlan]:
    return await _ops(run_dir).investigate(step, case, runtime)


@activity.defn(name="corsair.v2.build")
async def build(run_dir: str, step: str, case: Case, runtime: Runtime, plan: ProbePlan,
                feedback: str | None) -> StepResult[Recipe]:
    return await _ops(run_dir).build(step, case, runtime, plan, feedback)


@activity.defn(name="corsair.v2.replay")
async def replay(run_dir: str, step: str, case: Case, runtime: Runtime, recipe: Recipe,
                 revision: str) -> StepResult[Replayed]:
    return await _ops(run_dir).replay(step, case, runtime, recipe, revision)


@activity.defn(name="corsair.v2.probe")
async def probe(run_dir: str, step: str, brief: ProbeBrief, runtime: Runtime, case: Case, diagnostics: str | None,
                previous: ProbeDraft | None, review_feedback: str | None = None) -> StepResult[ProbeDraft]:
    return await _ops(run_dir).probe(step, brief, runtime, case, diagnostics, previous, review_feedback)


@activity.defn(name="corsair.v2.diagnose")
async def diagnose(run_dir: str, step: str, environment: Environment, runtime: Runtime, patch: FrozenPatch,
                   role: str) -> StepResult[Diagnosis]:
    return await _ops(run_dir).diagnose(step, environment, runtime, patch, role)


@activity.defn(name="corsair.v2.review")
async def review(run_dir: str, step: str, case: Case, plan: ProbePlan, patch: FrozenPatch,
                 revision: str, runtime: Runtime | None = None) -> StepResult[Validity]:
    return await _ops(run_dir).review(step, case, plan, patch, revision, runtime)


@activity.defn(name="corsair.v2.execute")
async def execute(run_dir: str, step: str, environment: Environment, runtime: Runtime, patch: FrozenPatch,
                  role: str, revision: str) -> StepResult[ProbeRun]:
    return await _ops(run_dir).execute(step, environment, runtime, patch, role, revision)


@activity.defn(name="corsair.v2.decide")
async def decide(run_dir: str, step: str, case: Case, runtime: Runtime | None, build: BuildResult | None,
                 plan: ProbePlan | None, validity: tuple[Validity, ...], runs: tuple[ProbeRun, ...],
                 stopped: str | None, fix_stopped: str | None = None) -> Verdict:
    return await _ops(run_dir).decide(step, case, runtime, build, plan, validity, runs, stopped, fix_stopped)


MODEL_ACTIVITIES = (ground, investigate, build, probe, review)
WORKSPACE_ACTIVITIES = (replay, diagnose, execute)
CONTROL_ACTIVITIES = (begin_run, finish_run, note_failure, select, decide)


# --- Workflow -----------------------------------------------------------------------------------------------------


class ActivityOps:
    """``compose``'s operations as activities. An activity-level failure is uncertain, so it is ``infra_error``."""

    def __init__(self, run_dir: str, grounding: bool):
        self.run_dir, self.grounding = run_dir, grounding

    async def _call(self, fn: Any, step: str, *args: Any, queue: str, timeout: timedelta, retry: RetryPolicy
                    ) -> StepResult:
        try:
            return await workflow.execute_activity(fn, args=[self.run_dir, step, *args], task_queue=queue,
                                                   start_to_close_timeout=timeout, retry_policy=retry)
        except ActivityError as exc:
            detail = f"{type(exc.cause).__name__ if exc.cause else 'ActivityError'}: {exc.cause or exc}"
            await workflow.execute_activity(note_failure, args=[self.run_dir, step, detail], task_queue=CONTROL_QUEUE,
                                            start_to_close_timeout=CONTROL_TIMEOUT, retry_policy=READ_RETRY)
            return StepResult(failure=TerminalReason.INFRA_ERROR, detail=detail)

    def _agent(self, fn: Any, step: str, *args: Any, timeout: timedelta = AGENT_TIMEOUT,
               retry: RetryPolicy = MODEL_RETRY):
        return self._call(fn, step, *args, queue=MODEL_QUEUE, timeout=timeout, retry=retry)

    def _container(self, fn: Any, step: str, *args: Any):
        return self._call(fn, step, *args, queue=WORKSPACE_QUEUE, timeout=CONTAINER_TIMEOUT, retry=ONCE)

    def ground(self, step, case):
        return self._agent(ground, step, case)

    def select(self, step, case):
        return self._call(select, step, case, queue=CONTROL_QUEUE, timeout=CONTROL_TIMEOUT, retry=READ_RETRY)

    def investigate(self, step, case, runtime):
        return self._agent(investigate, step, case, runtime)

    def build(self, step, case, runtime, plan, feedback):
        # The Builder runs shell commands in a container: exactly once.
        return self._agent(build, step, case, runtime, plan, feedback, timeout=BUILD_TIMEOUT, retry=ONCE)

    def replay(self, step, case, runtime, recipe, revision):
        return self._container(replay, step, case, runtime, recipe, revision)

    def probe(self, step, brief, runtime, case, diagnostics, previous, review_feedback=None):
        return self._agent(probe, step, brief, runtime, case, diagnostics, previous, review_feedback)

    def diagnose(self, step, environment, runtime, patch, role):
        return self._container(diagnose, step, environment, runtime, patch, role)

    def review(self, step, case, plan, patch, revision, runtime=None):
        return self._agent(review, step, case, plan, patch, revision, runtime)

    def execute(self, step, environment, runtime, patch, role, revision):
        return self._container(execute, step, environment, runtime, patch, role, revision)

    async def decide(self, step, case, runtime, build_result, plan, validity, runs, stopped,
                     fix_stopped=None) -> Verdict:
        return await workflow.execute_activity(
            decide, args=[self.run_dir, step, case, runtime, build_result, plan, validity, runs, stopped,
                          fix_stopped],
            task_queue=CONTROL_QUEUE, start_to_close_timeout=CONTROL_TIMEOUT, retry_policy=READ_RETRY)


@workflow.defn(name="corsair.v2.Investigation")
class InvestigationWorkflow:
    @workflow.run
    async def run(self, request: RunRequest) -> Verdict:
        bookend = {"task_queue": CONTROL_QUEUE, "start_to_close_timeout": CONTROL_TIMEOUT, "retry_policy": READ_RETRY}
        await workflow.execute_activity(begin_run, args=[request.run_dir, request.case], **bookend)
        verdict = await compose(request.case, ActivityOps(request.run_dir, request.grounding), request.budget)
        await workflow.execute_activity(finish_run, args=[request.run_dir, verdict], **bookend)
        return verdict


# --- Worker entry points ------------------------------------------------------------------------------------------


async def connect(address: str, namespace: str = "default"):
    from temporalio.client import Client
    from temporalio.contrib.pydantic import pydantic_data_converter

    return await Client.connect(address, namespace=namespace, data_converter=pydantic_data_converter)


def workers(client, *, workspace_slots: int = 4, queues: tuple[str, ...] = (MODEL_QUEUE, WORKSPACE_QUEUE,
                                                                             CONTROL_QUEUE)) -> list:
    """One worker per queue; a host may serve any subset (for example a second Docker host: workspace only)."""
    from temporalio.worker import Worker

    built = []
    if MODEL_QUEUE in queues:
        built.append(Worker(client, task_queue=MODEL_QUEUE, activities=list(MODEL_ACTIVITIES),
                            max_concurrent_activities=1))
    if WORKSPACE_QUEUE in queues:
        built.append(Worker(client, task_queue=WORKSPACE_QUEUE, activities=list(WORKSPACE_ACTIVITIES),
                            max_concurrent_activities=workspace_slots))
    if CONTROL_QUEUE in queues:
        built.append(Worker(client, task_queue=CONTROL_QUEUE, workflows=[InvestigationWorkflow],
                            activities=list(CONTROL_ACTIVITIES)))
    return built


async def serve(client, *, workspace_slots: int = 4) -> None:
    """Run all three workers until cancelled. ``configure`` must have run in this process."""
    if _CONFIG is None:
        raise RuntimeError("configure must run before serve")
    await asyncio.gather(*(worker.run() for worker in workers(client, workspace_slots=workspace_slots)))


async def run_workflow(client, request: RunRequest, *, workflow_id: str) -> Verdict:
    return await client.execute_workflow(InvestigationWorkflow.run, request, id=workflow_id, task_queue=CONTROL_QUEUE)
