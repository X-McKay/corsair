"""Direct-mode composition of the v2 chain (redesign sections 5 and 13).

Order: Ground (optional, advisory) -> Select -> Investigate -> Build (Builder episode in a disposable workspace,
then trusted replay in a fresh container; one more episode with the replay failure's tail if that fails, A2) ->
Probe (control and exploit, each from its own brief only) -> freeze -> D3 diagnose (each draft runs once; a
``not_run`` or ``errored`` author gets its own diagnostics for one revision, then the patch is re-frozen) ->
Review (outcome-blind, per revision) -> Execute (each probe once per revision) -> Decide (rule table).

The composition is split in two so direct and durable mode run the same logic:

- ``compose`` is the routing. It is deterministic given the step results, does no I/O and reads no clock, so the
  Temporal workflow runs it unchanged with activity-backed operations.
- ``LocalOps`` performs one step in-process: it calls the stage function, measures wall time around it, records
  input, output, usage and native message history, and turns exceptions into a terminal reason. Provider errors
  become ``provider_error``, usage-limit errors ``budget_exhausted`` and anything else ``infra_error``; nothing is
  retried here. The workflow's activities call ``LocalOps`` on the worker.

A stage that stops the chain passes its terminal reason to Decide as ``stopped``. One ``Budget`` covers the whole
run, corrections included (A2); it is never reset per stage. The grounding brief is recorded and never passed on.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import traceback
from collections.abc import Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.models import Model

from .contracts import (AgentUsage, BuildResult, Case, Environment, FrozenPatch, Outcome, ProbeBrief, ProbeDraft,
                        ProbePlan, ProbeRun, Recipe, Runtime, TerminalReason, Validity, Verdict)
from .record import RunRecorder
from .stages import BuildAgent, Decide, Diagnose, Execute, Investigate, Probe, Replay, Review, Select

T = TypeVar("T")
ROLES = ("control", "exploit")
LOG_TAIL = 4_000


class Budget(BaseModel):
    """One total budget for the run, checked before every agent call. Unknown usage counts as nothing spent."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    max_agent_calls: int = Field(default=12, ge=1)
    max_requests: int | None = Field(default=None, ge=1)
    max_tokens: int | None = Field(default=None, ge=1)


class StepResult(BaseModel, Generic[T]):
    """One step's output, the agent's usage (agent steps only) and, when the step stopped, why."""

    model_config = ConfigDict(frozen=True)
    output: T | None = None
    usage: AgentUsage | None = None
    failure: TerminalReason | None = None
    detail: str = ""


class Replayed(BaseModel):
    model_config = ConfigDict(frozen=True)
    build: BuildResult
    environment: Environment | None = None
    failure_tail: str = Field(default="", description="Reason and log tail, the feedback for one more episode")


class Diagnosis(BaseModel):
    model_config = ConfigDict(frozen=True)
    outcome: Outcome
    diagnostics: str | None = None


def draft_digest(draft: ProbeDraft) -> str:
    return hashlib.sha256(json.dumps(draft.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()


def freeze(control: ProbeDraft, exploit: ProbeDraft) -> FrozenPatch:
    """Both drafts under one digest; review and execution bind to it."""
    body = json.dumps([control.model_dump(mode="json"), exploit.model_dump(mode="json")], sort_keys=True)
    return FrozenPatch(control=control, exploit=exploit, sha256=hashlib.sha256(body.encode()).hexdigest())


# --- Stage implementations ---------------------------------------------------------------------------------------

Ground = Callable[[Any, Any, Model], Awaitable[tuple[Any, AgentUsage]]]
WorkspaceFactory = Callable[[Case, Runtime], AbstractAsyncContextManager[object]]


@dataclass(frozen=True)
class Stages:
    """One callable per stage, injected so the chain depends only on the shapes in ``stages.py``."""

    select: Select
    investigate: Investigate
    build: BuildAgent
    replay: Replay
    control_probe: Probe
    exploit_probe: Probe
    review: Review
    diagnose: Diagnose
    execute: Execute
    decide: Decide
    workspace: WorkspaceFactory
    ground: Ground | None = None
    grounding_context: Callable[[Case], Any] | None = None  # the configured context source; None skips Ground


def default_stages(*, grounding_context: Callable[[Case], Any] | None = None) -> Stages:
    """The real stage modules, imported only when a run needs them."""
    from .agents.builder import build
    from .agents.control_prober import probe as control_probe
    from .agents.exploit_prober import probe as exploit_probe
    from .agents.grounding import ground
    from .agents.investigator import investigate
    from .agents.reviewer import review
    from .build import replay
    from .execute import diagnose, run_probe
    from .matrix import select
    from .rules import decide

    return Stages(select=select, investigate=investigate, build=build, replay=replay, control_probe=control_probe,
                  exploit_probe=exploit_probe, review=review, diagnose=diagnose, execute=run_probe, decide=decide,
                  workspace=docker_workspace, ground=ground, grounding_context=grounding_context)


def docker_workspace(case: Case, runtime: Runtime) -> AbstractAsyncContextManager[object]:
    """The Builder's disposable workspace: the runtime image with the revision's tree copied in.

    Network is allowed only to the row's build hosts, when the row declares them.
    """
    from .workspace.docker import DockerWorkspace

    return DockerWorkspace(image=runtime.image, source=Path(case.revision.source),
                           network=tuple(getattr(runtime, "build_hosts", ())))


# --- One step, performed in-process -------------------------------------------------------------------------------

Progress = Callable[[str, str], None]


def _describe(exc: BaseException) -> str:
    return "".join(traceback.format_exception_only(type(exc), exc)).strip()[:4_000]


def _provider_errors() -> tuple[type[BaseException], ...]:
    import httpx
    import openai
    from pydantic_ai.exceptions import AgentRunError

    return (AgentRunError, openai.APIError, httpx.HTTPError, TimeoutError)


def _tail(build: BuildResult) -> str:
    """The replay failure the Builder sees in its one extra episode: the reason and the end of the log."""
    text = build.reason
    if build.log is not None:
        uri = build.log.uri.removeprefix("file://")
        path = Path(uri)
        if path.is_absolute() and path.is_file():
            data = path.read_bytes()[-LOG_TAIL:]
            text = f"{text}\n--- log tail ---\n{data.decode('utf-8', 'replace')}".strip()
    return text or "the replayed recipe did not pass the baseline test"


class LocalOps:
    """Performs each chain step in this process and records it. Also the body of every workflow activity."""

    def __init__(self, stages: Stages, models: Mapping[str, Model], matrix_path: Path, record: RunRecorder,
                 progress: Progress | None = None):
        self.stages, self.models, self.matrix_path = stages, models, Path(matrix_path)
        self.record, self.progress = record, progress
        self.grounding = stages.ground is not None and stages.grounding_context is not None

    def _report(self, step: str, text: str) -> None:
        if self.progress is not None:
            self.progress(step, text)

    async def _agent(self, step: str, agent: str, inputs: dict[str, Any],
                     call: Callable[[Model], Awaitable[tuple[Any, AgentUsage]]]) -> StepResult:
        from pydantic_ai import capture_run_messages
        from pydantic_ai.exceptions import UsageLimitExceeded
        from pydantic_ai.messages import ModelMessagesTypeAdapter

        model = self.models.get(agent)
        if model is None:
            raise ValueError(f"no model configured for agent {agent}")
        self._report(step, "started")
        output, usage, failure, error = None, None, None, None
        started = perf_counter()
        with capture_run_messages() as messages:
            try:
                output, usage = await call(model)
            except UsageLimitExceeded as exc:
                failure, error = TerminalReason.BUDGET_EXHAUSTED, _describe(exc)
            except _provider_errors() as exc:
                failure, error = TerminalReason.PROVIDER_ERROR, _describe(exc)
            except Exception as exc:  # a workspace or tool failure inside the episode; attributable, not a crash
                failure, error = TerminalReason.INFRA_ERROR, _describe(exc)
        wall = round(perf_counter() - started, 3)
        if usage is None:
            usage = AgentUsage(agent=agent, model=getattr(model, "model_name", None), wall_s=wall,
                               status="ok" if failure is None else failure.value)
        else:
            usage = usage.model_copy(update={"wall_s": wall})
        if failure is None and output is None and usage.status in ("provider_error", "budget_exhausted",
                                                                    "infra_error"):
            failure = TerminalReason(usage.status)
        messages_json = ModelMessagesTypeAdapter.dump_json(messages) if messages else None
        self.record.agent(step, usage, messages_json)
        self.record.stage(step, inputs={**inputs, "model": usage.model}, output=output, wall_s=wall, error=error)
        self._report(step, f"{failure.value if failure else usage.status} {wall:.1f}s")
        return StepResult(output=output, usage=usage, failure=failure, detail=error or "")

    async def _code(self, step: str, inputs: dict[str, Any], call: Callable[[], Any]) -> StepResult:
        output, failure, error = None, None, None
        started = perf_counter()
        try:
            output = await asyncio.to_thread(call)
        except Exception as exc:
            failure, error = TerminalReason.INFRA_ERROR, _describe(exc)
        wall = round(perf_counter() - started, 3)
        self.record.stage(step, inputs=inputs, output=output, wall_s=wall, error=error)
        self._report(step, f"{failure.value if failure else 'ok'} {wall:.1f}s")
        return StepResult(output=output, failure=failure, detail=error or "")

    async def ground(self, step: str, case: Case) -> StepResult[None]:
        stages = self.stages
        context = None

        async def call(model: Model):
            nonlocal context
            context = stages.grounding_context(case)
            return await stages.ground(case.finding, context, model)

        result = await self._agent(step, "grounding", {"finding": case.finding}, call)
        if result.output is not None:
            self.record.grounding(result.output)
        # Advisory only: the brief never leaves this step.
        return StepResult(usage=result.usage, failure=result.failure, detail=result.detail)

    async def select(self, step: str, case: Case) -> StepResult[Runtime]:
        return await self._code(step, {"case_id": case.case_id, "matrix": self.matrix_path},
                                lambda: self.stages.select(case, self.matrix_path))

    async def investigate(self, step: str, case: Case, runtime: Runtime) -> StepResult[ProbePlan]:
        return await self._agent(step, "investigator", {"case": case, "runtime": runtime},
                                 lambda model: self.stages.investigate(case, runtime, model,
                                                                       source_root=Path(case.revision.source)))

    async def build(self, step: str, case: Case, runtime: Runtime, plan: ProbePlan,
                    feedback: str | None) -> StepResult[Recipe]:
        async def call(model: Model):
            async with self.stages.workspace(case, runtime) as workspace:
                if feedback is None:
                    return await self.stages.build(case, runtime, plan, model, workspace=workspace)
                return await self.stages.build(case, runtime, plan, model, workspace=workspace, feedback=feedback)

        return await self._agent(step, "builder",
                                 {"case": case, "runtime": runtime, "plan": plan, "feedback": feedback}, call)

    async def replay(self, step: str, case: Case, runtime: Runtime, recipe: Recipe,
                     revision: str) -> StepResult[Replayed]:
        def call() -> Replayed:
            build, environment = self.stages.replay(case, runtime, recipe, revision=revision)
            ok = build.replayed and environment is not None
            return Replayed(build=build, environment=environment, failure_tail="" if ok else _tail(build))

        return await self._code(step, {"case_id": case.case_id, "runtime": runtime, "recipe": recipe,
                                       "revision": revision}, call)

    async def probe(self, step: str, brief: ProbeBrief, runtime: Runtime, case: Case, diagnostics: str | None,
                    previous: ProbeDraft | None) -> StepResult[ProbeDraft]:
        author = self.stages.control_probe if brief.role == "control" else self.stages.exploit_probe
        result = await self._agent(
            step, f"{brief.role}_prober",
            {"brief": brief, "runtime": runtime, "diagnostics": diagnostics, "previous": previous},
            lambda model: author(brief, runtime, model, source_root=Path(case.revision.source),
                                 diagnostics=diagnostics, previous=previous))
        draft = result.output
        if draft is not None and (draft.role, draft.test_file, draft.test_name) != (
                brief.role, brief.test_file, brief.test_name):
            return result.model_copy(update={"output": None, "detail": "draft does not match its brief"})
        if draft is not None and previous is not None and draft.revision_of is None:
            result = result.model_copy(update={"output": draft.model_copy(
                update={"revision_of": draft_digest(previous)})})
        return result

    async def diagnose(self, step: str, environment: Environment, runtime: Runtime, patch: FrozenPatch,
                       role: str) -> StepResult[Diagnosis]:
        def call() -> Diagnosis:
            outcome, diagnostics = self.stages.diagnose(environment, runtime, patch, role)
            keep = outcome in (Outcome.NOT_RUN, Outcome.ERRORED)
            return Diagnosis(outcome=outcome, diagnostics=diagnostics if keep else None)

        return await self._code(step, {"environment": environment, "patch_sha256": patch.sha256, "role": role}, call)

    async def review(self, step: str, case: Case, plan: ProbePlan, patch: FrozenPatch,
                     revision: str) -> StepResult[Validity]:
        source = case.revision if revision == "vulnerable" else case.fixed_revision
        result = await self._agent(
            step, "reviewer", {"case": case, "plan": plan, "patch": patch, "revision": revision},
            lambda model: self.stages.review(case, plan, patch, model, source_root=Path(source.source),
                                             revision=revision))
        validity = result.output
        if validity is not None and (validity.patch_sha256, validity.revision) != (patch.sha256, revision):
            return result.model_copy(update={"output": None, "detail": "validity bound to another patch or revision"})
        return result

    async def execute(self, step: str, environment: Environment, runtime: Runtime, patch: FrozenPatch, role: str,
                      revision: str) -> StepResult[ProbeRun]:
        return await self._code(step, {"environment": environment, "patch_sha256": patch.sha256, "role": role,
                                       "revision": revision},
                                lambda: self.stages.execute(environment, runtime, patch, role, revision=revision))

    async def decide(self, step: str, case: Case, runtime: Runtime | None, build: BuildResult | None,
                     plan: ProbePlan | None, validity: tuple[Validity, ...], runs: tuple[ProbeRun, ...],
                     stopped: str | None) -> Verdict:
        started = perf_counter()
        verdict = self.stages.decide(case, runtime=runtime, build=build, plan=plan, validity=validity, runs=runs,
                                     stopped=stopped)
        self.record.stage(step, inputs={"case_id": case.case_id, "runtime": runtime, "build": build, "plan": plan,
                                        "validity": validity, "runs": runs, "stopped": stopped},
                          output=verdict, wall_s=round(perf_counter() - started, 3))
        self._report(step, f"{verdict.label.value} {verdict.rule_id} {verdict.terminal_reason.value}")
        return verdict


# --- Routing (deterministic; shared by direct mode and the workflow) ---------------------------------------------


class _Stop(Exception):
    def __init__(self, reason: TerminalReason):
        super().__init__(reason.value)
        self.reason = reason


class _Composition:
    def __init__(self, case: Case, ops: Any, budget: Budget):
        self.case, self.ops, self.budget = case, ops, budget
        self.calls, self.requests, self.tokens = 0, 0, 0
        self.runtime: Runtime | None = None
        self.build: BuildResult | None = None
        self.plan: ProbePlan | None = None
        self.validity: list[Validity] = []
        self.runs: list[ProbeRun] = []

    async def agent(self, start: Callable[[], Awaitable[StepResult]], *, stop_on_failure: bool = True
                    ) -> StepResult:
        """Budget check before the call and charge after it; one total, never reset per stage (A2)."""
        b = self.budget
        if (self.calls >= b.max_agent_calls or (b.max_requests is not None and self.requests >= b.max_requests)
                or (b.max_tokens is not None and self.tokens >= b.max_tokens)):
            raise _Stop(TerminalReason.BUDGET_EXHAUSTED)
        result = await start()
        self.calls += 1
        if result.usage is not None:
            self.requests += result.usage.requests or 0
            self.tokens += (result.usage.input_tokens or 0) + (result.usage.output_tokens or 0)
        if result.failure is not None and stop_on_failure:
            raise _Stop(result.failure)
        return result

    async def code(self, start: Awaitable[StepResult]) -> StepResult:
        result = await start
        if result.failure is not None:
            raise _Stop(result.failure)
        return result

    async def run(self) -> Verdict:
        stopped: TerminalReason | None = None
        try:
            await self.steps()
        except _Stop as stop:
            stopped = stop.reason
        return await self.ops.decide("decide", self.case, self.runtime, self.build, self.plan, tuple(self.validity),
                                     tuple(self.runs), stopped.value if stopped else None)

    async def steps(self) -> None:
        case, ops = self.case, self.ops
        if ops.grounding:
            # Advisory: a failed grounding call is recorded and spends budget, but never stops the run.
            await self.agent(lambda: ops.ground("ground", case), stop_on_failure=False)

        runtime = (await self.code(ops.select("select", case))).output
        if runtime is None:
            raise _Stop(TerminalReason.NO_RUNTIME)
        self.runtime = runtime

        plan = (await self.agent(lambda: ops.investigate("investigate", case, runtime))).output
        self.plan = plan
        if plan is not None and plan.status == "unsupported_scope":
            raise _Stop(TerminalReason.UNSUPPORTED_SCOPE)
        if plan is None or plan.status != "planned" or plan.control is None or plan.exploit is None:
            raise _Stop(TerminalReason.PLAN_UNRESOLVED)

        environment = await self.prepare(runtime, plan)
        patch = await self.author(runtime, plan, environment)

        for revision in ("vulnerable", "fixed") if case.fixed_revision is not None else ("vulnerable",):
            validity = (await self.agent(lambda: ops.review(f"review-{revision}", case, plan, patch, revision))).output
            if validity is not None:
                self.validity.append(validity)

        await self.execute(environment, runtime, patch, "vulnerable")
        if case.fixed_revision is not None and self.build is not None and self.build.recipe is not None:
            # A fixed revision that does not replay leaves no fixed runs, so the fix stays not verified.
            fixed = await ops.replay("replay-fixed", case, runtime, self.build.recipe, "fixed")
            if fixed.failure is None and fixed.output.environment is not None and fixed.output.build.replayed:
                await self.execute(fixed.output.environment, runtime, patch, "fixed")

    async def prepare(self, runtime: Runtime, plan: ProbePlan) -> Environment:
        """One Builder episode, trusted replay, and at most one more episode fed the failure's tail (A2)."""
        ops, feedback = self.ops, None
        for step in ("build", "build-retry"):
            recipe = (await self.agent(lambda: ops.build(step, self.case, runtime, plan, feedback))).output
            if recipe is None:
                feedback = "The previous episode proposed no recipe."
                self.build = BuildResult(recipe=None, replayed=False, reason="the Builder proposed no recipe")
                continue
            replayed = (await self.code(ops.replay(f"replay-{step}", self.case, runtime, recipe, "vulnerable"))).output
            self.build = replayed.build
            if replayed.build.replayed and replayed.environment is not None:
                return replayed.environment
            feedback = replayed.failure_tail
        raise _Stop(TerminalReason.BUILD_FAILED)

    async def author(self, runtime: Runtime, plan: ProbePlan, environment: Environment) -> FrozenPatch:
        """Each Prober sees only its own brief; D3 gives a not_run or errored author one revision."""
        ops, case = self.ops, self.case
        briefs = {"control": plan.control, "exploit": plan.exploit}
        drafts: dict[str, ProbeDraft] = {}
        for role in ROLES:
            draft = (await self.agent(lambda: ops.probe(f"probe-{role}", briefs[role], runtime, case, None, None))
                     ).output
            if draft is None:
                raise _Stop(TerminalReason.PROBE_NOT_RUN)
            drafts[role] = draft
        patch = freeze(drafts["control"], drafts["exploit"])

        corrections: dict[str, str] = {}
        for role in ROLES:
            diagnosis = (await self.code(ops.diagnose(f"diagnose-{role}", environment, runtime, patch, role))).output
            if diagnosis.outcome in (Outcome.NOT_RUN, Outcome.ERRORED):
                corrections[role] = diagnosis.diagnostics or ""
        for role, diagnostics in corrections.items():
            revised = (await self.agent(lambda: ops.probe(f"probe-{role}-revision", briefs[role], runtime, case,
                                                          diagnostics, drafts[role]))).output
            if revised is not None:  # a failed correction leaves the original draft to be reviewed and run
                drafts[role] = revised
        return freeze(drafts["control"], drafts["exploit"]) if corrections else patch

    async def execute(self, environment: Environment, runtime: Runtime, patch: FrozenPatch, revision: str) -> None:
        for role in ROLES:
            run = (await self.code(self.ops.execute(f"execute-{role}-{revision}", environment, runtime, patch, role,
                                                    revision))).output
            self.runs.append(run)


async def compose(case: Case, ops: Any, budget: Budget = Budget()) -> Verdict:
    """The chain's routing over ``ops`` (``LocalOps`` in-process, or the workflow's activity-backed operations)."""
    return await _Composition(case, ops, budget).run()


async def run_case(case: Case, *, stages: Stages, models: Mapping[str, Model], matrix_path: Path,
                   record: RunRecorder, budget: Budget = Budget(), progress: Progress | None = None) -> Verdict:
    """Direct mode: one case through every stage in this process, recorded under ``record.run_dir``."""
    ops = LocalOps(stages, models, matrix_path, record, progress)
    needed = ["investigator", "builder", "control_prober", "exploit_prober", "reviewer"]
    missing = [agent for agent in needed + (["grounding"] if ops.grounding else []) if agent not in models]
    if missing:
        raise ValueError(f"no model configured for agents: {', '.join(missing)}")
    record.begin(case, mode="direct")
    verdict = await compose(case, ops, budget)
    record.finish(verdict)
    return verdict


__all__ = ["Budget", "Diagnosis", "LocalOps", "Replayed", "Stages", "StepResult", "compose", "default_stages",
           "draft_digest", "freeze", "run_case"]
