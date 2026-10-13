"""E2E-0 composition: runtime selection, identification, planning, authoring, frozen execution, assessment, gates.

Each stage reuses its own factory and typed contract; routing is a total match on the previous
stage's status, every abstention stops the run with its reason, and nothing loops between
stages. Runtime selection (SPEC-0060) runs first when the case carries build files and ends the run
before any model request unless a prepared matrix row supports the project; environment evidence is
still operator-supplied (IDEA-0004) and must name the selected image. The gate verdict is computed
from the frozen evidence whether or not the assessment agent completes. ``run_chain`` holds the
routing for every mode over injected stage and revision ports; ``run_direct`` binds them in-process
and the durable chain (``corsair.workflows.chain``) binds child workflows and activities.
"""

import asyncio
import re
from dataclasses import dataclass, field, replace
from functools import partial
from time import perf_counter
from typing import Any, Awaitable, Callable, Literal, Protocol
from uuid import UUID, uuid4

from pydantic import Field
from pydantic_ai import Agent, capture_run_messages
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model
from pydantic_ai.usage import RunUsage, UsageLimits

from corsair.agents.environment.agent import create_environment_agent, environment_prompt
from corsair.agents.environment.contracts import (BlockedEnvironment, EnvironmentInput, ReadyEnvironment, Toolchain,
                                                  UnsupportedEnvironment)
from corsair.agents.environment.dependencies import EnvironmentDependencies, SetupBudget
from corsair.agents.evidence_assessment.agent import assessment_prompt, create_evidence_assessment_agent
from corsair.agents.evidence_assessment.contracts import WINDOW_LINES, AssessmentInput, EvidenceAssessment
from corsair.agents.evidence_assessment.dependencies import AssessmentDependencies
from corsair.agents.issue_analysis.contracts import IssueAnalysisInput, SourceFile
from corsair.agents.issue_identification import create_issue_identification_agent, identification_prompt
from corsair.agents.issue_identification.contracts import IssueIdentification
from corsair.agents.issue_analysis.tools import FixtureDependencies
from corsair.agents.source.contracts import Contract
from corsair.agents.source.tools import READ_LINE_LIMIT
from corsair.agents.test_authoring.agent import authoring_prompt, create_test_authoring_agent
from corsair.agents.test_authoring.contracts import TestAuthoringInput, TestPatch
from corsair.agents.test_authoring.dependencies import AuthoringBudget, AuthoringDependencies
from corsair.agents.test_planning.agent import create_test_planning_agent
from corsair.agents.test_planning.dependencies import PlanningDependencies
from corsair.agents.test_planning.prompts import planning_prompt
from corsair.agents.test_planning.contracts import EnvironmentEvidence, ReadyTestPlan, TestPlanningInput
from corsair.core.disposition import AssessmentEvidence, EnvironmentIdentity, GateResult, ObservationPlan, assess
from corsair.nodes.runtime.contracts import RuntimeInputs, RuntimeOutcome
from corsair.nodes.runtime.environment import RuntimeCatalog, check_ready, ready_evidence, select_runtime
from corsair.nodes.witness import WitnessEvidence, witness_evidence
from corsair.ports.execution import SandboxExecution
from corsair.ports.sandbox import SandboxHandle
from corsair.ports.test_runner import ApprovedPatch, NativeTestRun, PatchFile, TestRunner, WitnessRequest

from .evidence import evidence_items, freeze, observation_plan, run_evidence, witness_request
from .progress import (Activity, GateDecided, RevisionEnded, RevisionStarted, RunEnded, RunEvent, RunObserver,
                       StageEnded, StageStarted, Usage, clean, current_observer, ignore)

Stage = Literal["runtime", "environment", "identification", "planning", "authoring", "execution", "assessment"]
AgentStage = Literal["environment", "identification", "planning", "authoring", "assessment"]
Purpose = Literal["development", "baseline", "candidate"]


class StageLimits(Contract):
    """One stage run's caps, derived from its own input and recorded in its receipt (SPEC-0043)."""
    request_limit: int = Field(strict=True, gt=0)
    tool_calls_limit: int = Field(strict=True, ge=0)
    total_tokens_limit: int = Field(strict=True, gt=0)
    timeout_seconds: float = Field(gt=0, allow_inf_nan=False)
    # Derivation: windows needed to read the stage's readable inputs once, plus input-sized work calls.
    read_windows: int = Field(strict=True, ge=0)
    work_tool_calls: int = Field(strict=True, ge=0)

    def usage_limits(self) -> UsageLimits:
        return UsageLimits(request_limit=self.request_limit, tool_calls_limit=self.tool_calls_limit,
                           total_tokens_limit=self.total_tokens_limit)


class StageBudget(Contract):
    """Operator-owned per-stage ceilings and derivation; the provider configuration owns the response cap.

    A run's tool calls are its read windows plus its work calls plus ``slack_tool_calls``; requests are
    those calls plus the output request and its retries plus one; tokens are ``tokens_per_request`` per
    request. Each is capped by the ceiling here, so a derived cap never exceeds what the operator admitted.
    """
    request_limit: int = Field(strict=True, gt=0, le=64)
    tool_calls_limit: int = Field(strict=True, ge=0, le=48)
    total_tokens_limit: int = Field(strict=True, gt=0, le=262144)
    timeout_seconds: float = Field(gt=0, le=1800, allow_inf_nan=False)
    slack_tool_calls: int = Field(default=2, strict=True, ge=0, le=8)
    tokens_per_request: int = Field(default=12000, strict=True, gt=0, le=32768)

    def limits(self, read_windows: int, work_tool_calls: int, output_retries: int) -> StageLimits:
        tools = min(read_windows + work_tool_calls + self.slack_tool_calls, self.tool_calls_limit)
        requests = min(tools + output_retries + 2, self.request_limit)
        return StageLimits(request_limit=requests, tool_calls_limit=tools,
                           total_tokens_limit=min(requests * self.tokens_per_request, self.total_tokens_limit),
                           timeout_seconds=self.timeout_seconds, read_windows=read_windows,
                           work_tool_calls=work_tool_calls)


class CompositionBudget(Contract):
    # The environment agent's isolated eval budget (evals/environment EvaluationBudget), not wider (SPEC-0068).
    environment: StageBudget = StageBudget(request_limit=16, tool_calls_limit=20, total_tokens_limit=48000,
                                           timeout_seconds=240, tokens_per_request=8000)
    setup_commands: int = Field(default=12, strict=True, ge=1, le=16)
    identification: StageBudget = StageBudget(request_limit=20, tool_calls_limit=16, total_tokens_limit=128000,
                                              timeout_seconds=300, tokens_per_request=8000)
    planning: StageBudget = StageBudget(request_limit=20, tool_calls_limit=16, total_tokens_limit=160000,
                                        timeout_seconds=600, tokens_per_request=10000)
    authoring: StageBudget = StageBudget(request_limit=32, tool_calls_limit=28, total_tokens_limit=262144,
                                         timeout_seconds=900, slack_tool_calls=2, tokens_per_request=12000)
    assessment: StageBudget = StageBudget(request_limit=32, tool_calls_limit=28, total_tokens_limit=262144,
                                          timeout_seconds=600, slack_tool_calls=3, tokens_per_request=10000)
    dev_runs: int = Field(default=3, strict=True, ge=1, le=5)
    output_retries: int = Field(default=1, strict=True, ge=0, le=1)
    admission_refusals: int = Field(default=1, strict=True, ge=0, le=2)


Limit = Literal["request_limit", "tool_calls_limit", "total_tokens_limit", "timeout_seconds"]


class BudgetExhausted(Contract):
    """The typed outcome of a stage that ended on one of its own caps instead of returning its output."""
    status: Literal["budget_exhausted"] = "budget_exhausted"
    stage: Literal["environment", "identification", "planning", "authoring", "assessment"]
    limit: Limit
    cap: float
    limits: StageLimits


def _windows(contents, window: int = READ_LINE_LIMIT) -> int:
    return sum(-(-len(content.splitlines()) // window) or 1 for content in contents)


def stage_limits(stage: "AgentStage", inputs: Any, budget: "CompositionBudget") -> StageLimits:
    """Caps from the task: each readable input once in tool windows, plus the stage's own work calls."""
    match stage:
        case "environment":
            # Each setup source once, list_toolchains once, and every setup command the operator admits.
            reads, work = _windows(source.content for source in inputs.source_files), budget.setup_commands + 1
        case "identification" | "planning":
            reads, work = _windows(source.content for source in inputs.source_files), 0
        case "authoring":
            # Per development run: up to two writes of each planned test path and the run itself; plus each
            # admission refusal the author may act on.
            paths = {inputs.plan.control.test_path, inputs.plan.security.test_path}
            reads = _windows(source.content for source in inputs.source_files)
            work = budget.dev_runs * (2 * len(paths) + 1) + budget.admission_refusals
        case "assessment":
            reads, work = _windows((item.content for item in inputs.items), WINDOW_LINES), 0
    return getattr(budget, stage).limits(reads, work, budget.output_retries)


def cap_reached(limits: StageLimits | None, usage: RunUsage | None) -> bool:
    """Whether the run spent its tool-call cap; recorded on every attempt, whatever ended it."""
    return limits is not None and usage is not None and usage.tool_calls >= limits.tool_calls_limit


def exhaustion(stage: "AgentStage", limits: StageLimits, failure: BaseException | None, *,
               deadline: bool = False) -> BudgetExhausted | None:
    """Which cap ended a stage that returned no output; None when it failed for another reason.

    Only the native limit errors are evidence of a cap: a call to a tool withdrawn at the cap is refused by
    PydanticAI as UsageLimitExceeded naming tool_calls_limit. Every other failure, an UnexpectedModelBehavior
    after the cap included (spent output retries or a malformed provider response), keeps its own
    classification; whether the cap was reached is recorded separately as tool_cap_reached. A TimeoutError is
    the stage's ``timeout_seconds`` only when ``deadline`` says the stage's own deadline fired: a provider, tool
    or activity timeout inside the stage stays that layer's failure.
    """
    if failure is None:
        return None
    kind = failure.kind if isinstance(failure, RecordedFailure) else type(failure).__name__
    limit: Limit | None = None
    if kind == "TimeoutError" and deadline:
        limit = "timeout_seconds"
    elif kind == "UsageLimitExceeded":
        limit = next((name for name in ("tool_calls_limit", "total_tokens_limit", "request_limit")
                      if name in str(failure)), "request_limit")
    if limit is None:
        return None
    return BudgetExhausted(stage=stage, limit=limit, cap=getattr(limits, limit), limits=limits)


@dataclass(frozen=True)
class StageModels:
    """One explicit model per stage; the same instance may serve several stages."""
    identification: Model
    planning: Model
    authoring: Model
    assessment: Model
    environment: Model | None = None  # Needed only by cases that carry setup source (SPEC-0068)


class Runners(Protocol):
    """Operator-owned: a fresh-workspace runner for authoring development runs and for each frozen revision."""
    def __call__(self, purpose: Purpose) -> TestRunner: ...


class SetupSource(Contract):
    """SPEC-0068: the agent-visible setup source of the baseline revision; never labels or oracles."""
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_private: bool
    source_files: tuple[SourceFile, ...] = Field(min_length=1, max_length=32)
    policy_profile: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9._-]*$")


@dataclass(frozen=True)
class PreparedSandbox:
    """A sandbox of one prepared toolchain image, live until the preparation port releases it.

    ``read_source`` returns a file's bytes from the operator's capture of the revision placed in the sandbox
    (never from the sandbox), or None when the capture has no such file; ``source_paths`` lists every file of that
    capture (SPEC-0071: without it a smoke baseline is refused)."""
    execution: SandboxExecution
    handle: SandboxHandle
    scratch_location: str
    read_source: Callable[[str], bytes | None]
    source_paths: Callable[[], tuple[str, ...]] | None = None


class Preparation(Protocol):
    """Operator-owned sandbox lifecycle for the environment stage; adapters are chosen outside the chain."""
    def prepare(self, toolchain: Toolchain, operation: UUID, *, overlay: tuple[PatchFile, ...] = ()) -> PreparedSandbox:
        """`overlay`: operator files (SPEC-0071 smoke tests) written beside the captured commit; an overlay path the
        capture already has is refused before any sandbox is created."""
        ...
    def release(self, sandbox: PreparedSandbox, operation: UUID) -> Literal["confirmed", "unconfirmed"]: ...


@dataclass(frozen=True)
class FixtureCase:
    """Operator inputs: the issue over the baseline revision's saved source, and hand-supplied environment facts."""
    issue: IssueAnalysisInput
    environment: EnvironmentEvidence
    environment_identity: EnvironmentIdentity
    # Operator-known digest of each revision's captured source; a run from any other source is refused.
    revision_sources: dict[Literal["baseline", "candidate"], str]
    # Operator-approved probe target and planned effect file; without it no witness is requested unless
    # `witness_from_recorders` lets the environment's operator witness facilities bind one (SPEC-0073).
    witness_envelope: WitnessRequest | None = None
    witness_from_recorders: bool = False
    # The baseline revision's build files (SPEC-0060); without them the runtime is the operator's declaration.
    runtime: RuntimeInputs | None = None
    # The baseline revision's setup source (SPEC-0068); with it the environment agent prepares the environment.
    setup: SetupSource | None = None


@dataclass(frozen=True)
class StageAttempt:
    stage: Stage
    output: Any
    usage: RunUsage | None  # None: not observed, as for a durable stage that closed without returning
    messages: tuple[ModelMessage, ...]
    elapsed_seconds: float
    failure: BaseException | None
    limits: StageLimits | None = None  # None: refused before its limits were derived
    exhausted: BudgetExhausted | None = None
    cleanup: Literal["confirmed", "unconfirmed"] | None = None  # The environment stage's sandbox; None elsewhere
    messages_omitted: bool = False  # Durable environment stage: its record would not fit the activity payload
    # The ready environment's baseline test file from the operator's capture; planning and authoring need it.
    baseline_source: SourceFile | None = None
    baseline_refusal: str | None = None  # Why the capture could not supply that file as saved source

    @property
    def tool_cap_reached(self) -> bool:
        return cap_reached(self.limits, self.usage)


@dataclass(frozen=True)
class FrozenExecution:
    revision: Literal["baseline", "candidate"]
    operation: UUID
    observed: NativeTestRun | None
    failure: BaseException | None


@dataclass(frozen=True)
class DirectRun:
    """Everything the run produced; ``stopped_at`` names the stage whose outcome ended it, if any."""
    stopped_at: Stage | None
    reason: str
    attempts: tuple[StageAttempt, ...]
    identification: IssueIdentification | None = None
    plan: ReadyTestPlan | None = None
    patch: TestPatch | None = None
    observation_plan: ObservationPlan | None = None
    executions: tuple[FrozenExecution, ...] = ()
    gate: GateResult | None = None
    assessment: EvidenceAssessment | None = None
    witnesses: tuple[WitnessEvidence, ...] = ()
    limitations: tuple[str, ...] = field(default=())
    runtime: RuntimeOutcome | None = None
    environment: ReadyEnvironment | BlockedEnvironment | UnsupportedEnvironment | None = None


class RecordedFailure(Exception):
    """A failure observed in another process, kept as its native type name and message; never re-raised there."""
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


# Mode ports: a stage invoker returns the attempt it made; a revision executor runs one frozen revision
# once and raises if nothing was observed. Neither retries.
StageInvoker = Callable[[AgentStage, Any], Awaitable[StageAttempt]]
# Answers the runtime stage once from the operator's catalog; raises when it cannot select at all.
RuntimeSelector = Callable[[RuntimeInputs], Awaitable[RuntimeOutcome]]
NO_CATALOG = "The case carries build files but no runtime catalog is configured"


class RuntimeCatalogMissing(ValueError):
    """The same failure kind in every mode: the durable activity raises it as an ApplicationError type."""


NO_PREPARATION = "The case carries setup source but no environment model or sandbox preparation is configured"


class PreparationMissing(ValueError):
    """A case needs the environment stage and the mode has no environment model or sandbox preparation."""


class RevisionExecutor(Protocol):
    async def __call__(self, revision: Literal["baseline", "candidate"], patch: ApprovedPatch, *, control_test_id: str,
                       security_test_id: str, discovery_command: tuple[str, ...], operation: UUID,
                       witness: WitnessRequest | None = None) -> NativeTestRun: ...


AGENTS = {"environment": create_environment_agent, "identification": create_issue_identification_agent,
          "planning": create_test_planning_agent,
          "authoring": create_test_authoring_agent, "assessment": create_evidence_assessment_agent}


def stage_call(stage: AgentStage, inputs: Any, budget: CompositionBudget, runner: TestRunner | None) -> tuple[str, Any]:
    """Prompt and dependencies for one stage; the mode supplies the authoring stage's development runner."""
    match stage:
        case "environment":
            raise ValueError("the environment stage's dependencies hold a live sandbox; the mode builds them")
        case "identification":
            return identification_prompt(inputs), FixtureDependencies(inputs)
        case "planning":
            return planning_prompt(inputs), PlanningDependencies(inputs)
        case "authoring":
            return authoring_prompt(inputs), AuthoringDependencies(inputs, runner, AuthoringBudget(
                dev_runs=budget.dev_runs, admission_refusals=budget.admission_refusals))
        case "assessment":
            return assessment_prompt(inputs), AssessmentDependencies(inputs)


async def _invoke(stage: AgentStage, agent: Agent[Any, Any], prompt: str, deps: Any, limits: StageLimits,
                  observe: RunObserver | None = None) -> StageAttempt:
    usage, messages, output, failure = RunUsage(), [], None, None
    started = perf_counter()
    deadline = asyncio.timeout(limits.timeout_seconds)
    # SPEC-0072: an observed stage reports its turns and tool calls through PydanticAI's capability hooks.
    watched = {"capabilities": [Activity(stage, observe, limits, started)]} if observe else {}
    try:
        with capture_run_messages() as messages:
            async with deadline:
                output = (await agent.run(prompt, deps=deps, usage=usage, usage_limits=limits.usage_limits(),
                                          **watched)).output
    except Exception as exc:
        failure = exc
    return StageAttempt(stage, output, usage, tuple(messages), perf_counter() - started, failure, limits,
                        exhaustion(stage, limits, failure, deadline=deadline.expired()))


async def prepare_environment(inputs: EnvironmentInput, model: Model | None, preparation: Preparation | None,
                              budget: CompositionBudget, observe: RunObserver | None = None) -> StageAttempt:
    """The environment stage, once and in one process in every mode: prepare a sandbox of the selected toolchain,
    run the environment agent there and release it. The setup ledger and live sandbox never leave this call."""
    limits = stage_limits("environment", inputs, budget)
    if preparation is None or model is None:
        return StageAttempt("environment", None, None, (), 0.0, PreparationMissing(NO_PREPARATION), limits)
    (selected,), operation, started = inputs.toolchains, uuid4(), perf_counter()
    try:
        overlay = tuple(PatchFile(t.path, t.content.encode()) for t in inputs.smoke_tests)
        sandbox = await asyncio.to_thread(partial(preparation.prepare, overlay=overlay), selected, operation)
    except Exception as exc:
        # Nothing was handed back to release; whether a sandbox exists is the adapter's to report.
        return StageAttempt("environment", None, None, (), perf_counter() - started, exc, limits, cleanup="unconfirmed")
    try:
        agent = AGENTS["environment"](model, output_retries=budget.output_retries)
        deps = EnvironmentDependencies(inputs=inputs, execution=sandbox.execution, handle=sandbox.handle,
                                       toolchain_id=selected.toolchain_id, scratch_location=sandbox.scratch_location,
                                       budget=SetupBudget(max_commands=budget.setup_commands), new_operation=uuid4,
                                       checkout_paths=sandbox.source_paths() if sandbox.source_paths else None)
        attempt = await _invoke("environment", agent, environment_prompt(inputs), deps, limits, observe)
        if isinstance(attempt.output, ReadyEnvironment):
            # SPEC-0071: a smoke baseline is the operator's overlay file, so its saved source is the template itself.
            smoke = next((t for t in inputs.smoke_tests if t.path == attempt.output.baseline_test_path), None)
            source, refusal = (SourceFile(path=smoke.path, content=smoke.content), None) if smoke else \
                captured(sandbox, attempt.output.baseline_test_path)
            attempt = replace(attempt, baseline_source=source, baseline_refusal=refusal)
    except Exception as exc:
        attempt = StageAttempt("environment", None, None, (), perf_counter() - started, exc, limits)
    finally:
        try:
            cleanup = await asyncio.to_thread(preparation.release, sandbox, operation)
        except Exception:
            cleanup = "unconfirmed"
    return replace(attempt, cleanup="confirmed" if cleanup == "confirmed" else "unconfirmed")


SOURCE_CHARACTERS = SourceFile.model_fields["content"].metadata[0].max_length


def captured(sandbox: PreparedSandbox, path: str) -> tuple[SourceFile | None, str | None]:
    """One file of the captured revision as saved source, or why it cannot be: missing, not UTF-8, or larger than
    the saved-source contract holds per file."""
    try:
        data = sandbox.read_source(path)
    except Exception as exc:
        return None, f"could not be read from the capture: {type(exc).__name__}"
    if data is None:
        return None, "is not in the captured revision"
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None, "is not UTF-8 text"
    if len(text) > SOURCE_CHARACTERS:
        return None, f"is {len(text)} characters; saved source holds at most {SOURCE_CHARACTERS} per file"
    try:
        return SourceFile(path=path, content=text), None
    except ValueError as exc:
        return None, f"is not admissible saved source: {exc}"[:512]


# Recorded on every run that reaches the gates, because nothing below observes them.
UNOBSERVED = ("The witness probe runs inside the test interpreter: it is operator-owned and tamper-evident, not "
              "tamper-proof against hostile test code.",
              "Sandbox events are observed only as permission errors raised on the witness path; policy or resource "
              "events elsewhere are not observed.",
              "Environment identity is the operator's declaration for both revisions, not an observed image or "
              "dependency digest.")
SMOKE_BASELINE = ("Baseline test is the operator smoke test: the project ships no test that ran. It shows that the "
                  "runtime, framework and discovery work after setup, not that the project's own code loads.")
UNSELECTED = "Runtime not selected from build files: the runtime is the operator's declaration."
MESSAGES_OMITTED = "environment stage messages omitted: the encoded stage record exceeded its payload bound"
OBSERVED_IDENTITY = ("Environment image and recipe observed by the environment stage; scratch location, dependency "
                     "inventory, policy revision and limits are the operator's declaration.",
                     "Revisions run on the operator's runners, not in the environment stage's prepared sandbox.")


async def run_direct(case: FixtureCase, models: StageModels, runners: Runners,
                     budget: CompositionBudget = CompositionBudget(), *, catalog: RuntimeCatalog | None = None,
                     preparation: Preparation | None = None, observe: RunObserver | None = None) -> DirectRun:
    """One E2E-0 investigation over a baseline and candidate revision; never retries a stage.

    ``catalog`` is the operator's runtime matrix and prepared images; a case with build files needs it.
    ``preparation`` prepares the environment stage's sandbox; a case with setup source needs it and
    ``models.environment``. ``observe`` (default: the one ``progress.observing`` set, if any) receives the
    run's activity (SPEC-0072)."""
    observe = observe or current_observer()

    async def invoke(stage: AgentStage, inputs: Any) -> StageAttempt:
        if stage == "environment":
            return await prepare_environment(inputs, models.environment, preparation, budget, observe)
        agent = AGENTS[stage](getattr(models, stage), output_retries=budget.output_retries)
        prompt, deps = stage_call(stage, inputs, budget, runners("development") if stage == "authoring" else None)
        return await _invoke(stage, agent, prompt, deps, stage_limits(stage, inputs, budget), observe)

    async def execute(revision, patch, **request) -> NativeTestRun:
        return runners(revision).run(patch, **request)

    async def select(inputs: RuntimeInputs) -> RuntimeOutcome:
        if catalog is None:
            raise RuntimeCatalogMissing(NO_CATALOG)
        return select_runtime(inputs, catalog)

    return await run_chain(case, invoke, execute, select, new_operation=uuid4, observe=observe or ignore)


# Spellings of an admitted framework's name that the grammar below cannot read: "JUnit Jupiter 5.10" is JUnit 5.
FRAMEWORK_ALIASES = (("junit jupiter", "junit"),)
DECLARED_FRAMEWORK = re.compile(r"(?P<name>[a-z]+(?:-[a-z]+)*)(?:[ _-]?v?(?P<major>[0-9]+)(?:\.[0-9]+)*)?")


def framework_names(declared: str) -> set[str]:
    """The framework ids a declaration can name: its name, and its name with its major version; none when the
    declaration is not a name with at most a version suffix."""
    declared = declared.strip().casefold()
    declared = next((name + declared[len(alias):] for alias, name in FRAMEWORK_ALIASES if declared.startswith(alias)),
                    declared)
    parsed = DECLARED_FRAMEWORK.fullmatch(declared)
    return {parsed["name"], parsed["name"] + (parsed["major"] or "")} if parsed else set()


def declared_mismatch(case: FixtureCase, outcome: RuntimeOutcome) -> str | None:
    """Why the operator's declared environment is not the selected row's prepared image, if it is not."""
    digest = outcome.image.rsplit("@sha256:", 1)[1]
    language = outcome.requirement.language
    if case.environment_identity.image_digest != digest:
        return (f"declared environment image {case.environment_identity.image_digest} is not the selected "
                f"{outcome.selection.image_id} image {outcome.image}")
    if case.environment.language.casefold() != language:
        return f"declared environment language {case.environment.language} is not the selected {language}"
    # A framework name with at most a version suffix: "pytest 9.0.3" names pytest, "JUnit 5" and "JUnit 4.12" name
    # junit5 and junit4, "tap-harness 3.42" names tap-harness; "pytest-bdd" names no admitted framework.
    admitted = sorted(c.name for c in outcome.selection.checks if c.kind == "test_framework" and c.satisfied)
    if not framework_names(case.environment.framework) & set(admitted):
        return f"declared environment framework {case.environment.framework} is not one the selection admitted ({', '.join(admitted)})"
    return None


async def run_chain(case: FixtureCase, invoke: StageInvoker, execute: RevisionExecutor, select: RuntimeSelector, *,
                    new_operation: Callable[[], UUID], observe: RunObserver = ignore) -> DirectRun:
    """Mode-independent routing: each stage at most once, revisions once each, gates over frozen evidence.

    ``observe`` receives each stage's start and end, each revision run and the gate (SPEC-0072); it never
    changes the routing."""
    attempts: list[StageAttempt] = []
    issue, environment, identity = case.issue, case.environment, case.environment_identity
    source_files = issue.source_files
    runtime, selected, prepared, provenance = None, (UNSELECTED,), None, UNOBSERVED[2:]
    # What the environment stage could not confirm or keep; every later stop carries it.
    stage_notes: tuple[str, ...] = ()

    def report(event: Callable[[], RunEvent]) -> None:
        # Built only when someone watches, and never able to end or reroute the run (SPEC-0072).
        if observe is not ignore:
            try:
                observe(event())
            except Exception:
                pass

    async def _stage(stage: AgentStage, inputs: Any) -> Any:
        report(lambda: StageStarted(stage))
        attempts.append(await invoke(stage, inputs))
        return attempts[-1].output

    def spent(stage: Stage) -> Usage | None:
        attempt = attempts[-1] if attempts and attempts[-1].stage == stage else None
        if attempt is None or attempt.usage is None:
            return None
        limits = attempt.limits
        return Usage(attempt.usage.requests, attempt.usage.tool_calls, attempt.usage.total_tokens,
                     attempt.elapsed_seconds, limits and limits.request_limit, limits and limits.tool_calls_limit,
                     limits and limits.total_tokens_limit, limits and limits.timeout_seconds)

    def ready(stage: Stage, detail: Callable[[], str]) -> None:
        report(lambda: StageEnded(stage, "ready", clean(detail()), spent(stage)))

    def stop(stage: Stage, reason: str, **values) -> DirectRun:
        values.setdefault("limitations", stage_notes)
        report(lambda: StageEnded(stage, "stopped", clean(reason, 2048), spent(stage)))
        report(lambda: RunEnded(stage, clean(reason, 2048), values["gate"] and verdict(values["gate"].permitted)
                                if "gate" in values else None))
        return DirectRun(stopped_at=stage, reason=reason, attempts=tuple(attempts), runtime=runtime,
                         environment=prepared, **values)

    def failure_of(stage: Stage) -> str:
        exhausted = attempts[-1].exhausted
        if exhausted is not None:
            return (f"{stage} budget exhausted: {exhausted.limit} {exhausted.cap:g} "
                    f"(derived from {exhausted.limits.read_windows} read windows and "
                    f"{exhausted.limits.work_tool_calls} work calls)")
        failed = attempts[-1].failure
        kind = failed.kind if isinstance(failed, RecordedFailure) else type(failed).__name__
        return f"{stage} produced no output: {kind}: {failed}"[:2048]

    if case.runtime is not None:
        report(lambda: StageStarted("runtime"))
        try:
            runtime = await select(case.runtime)
        except Exception as exc:
            kind = exc.kind if isinstance(exc, RecordedFailure) else type(exc).__name__
            return stop("runtime", f"runtime selection failed: {kind}: {exc}"[:2048])
        if runtime.status != "supported":
            return stop("runtime", runtime.reason)
        if case.setup is None and (mismatch := declared_mismatch(case, runtime)):
            return stop("runtime", mismatch[:2048])
        selected = ("Runtime selected from the baseline revision's build files; the candidate's were not read.",)
        ready("runtime", lambda: f"{runtime.selection.image_id} ({runtime.requirement.language})")

    if case.setup is not None:
        # SPEC-0068: the environment agent prepares the selected toolchain; its admitted result replaces the declaration.
        if runtime is None:
            return stop("environment", "setup source needs a runtime selected from build files; the case carries none")
        try:
            environment_input = EnvironmentInput(toolchains=(runtime.toolchain,), smoke_tests=runtime.smoke_tests,
                                                 **case.setup.model_dump())
        except ValueError as exc:
            return stop("environment", f"environment input refused: {exc}"[:2048])
        result = await _stage("environment", environment_input)
        unconfirmed = ((("environment sandbox cleanup unconfirmed",) if attempts[-1].cleanup == "unconfirmed" else ())
                       + ((MESSAGES_OMITTED,) if attempts[-1].messages_omitted else ()))
        if not isinstance(result, (ReadyEnvironment, BlockedEnvironment, UnsupportedEnvironment)):
            return stop("environment", failure_of("environment"), limitations=unconfirmed)
        prepared = result
        if isinstance(result, BlockedEnvironment):
            codes = ", ".join(d.code for d in result.diagnostics)
            return stop("environment", (f"environment blocked at {result.layer}: {result.evidence}"
                                        + (f" ({codes})" if codes else ""))[:2048], limitations=unconfirmed)
        if isinstance(result, UnsupportedEnvironment):
            return stop("environment", f"environment unsupported: {result.requirement}"[:2048], limitations=unconfirmed)
        try:
            check_ready(result, runtime.selection, {runtime.selection.image_id: runtime.image})
            environment, identity = ready_evidence(result, case.environment, case.environment_identity)
        except ValueError as exc:
            return stop("environment", f"ready environment refused: {exc}"[:2048], limitations=unconfirmed)
        provenance, stage_notes = OBSERVED_IDENTITY + unconfirmed, unconfirmed
        if result.baseline_basis == "operator_smoke":
            provenance += (SMOKE_BASELINE,)
        # The agent chose the baseline test while the case ran; its file joins the saved inventory from the capture.
        if result.baseline_test_path not in {source.path for source in source_files}:
            baseline = attempts[-1].baseline_source
            if baseline is None or baseline.path != result.baseline_test_path:
                why = attempts[-1].baseline_refusal or "was not read from the capture"
                return stop("environment", f"ready environment refused: baseline test file "
                                           f"{result.baseline_test_path} {why}"[:2048])
            source_files += (baseline,)
        ready("environment", lambda: f"{result.language} {result.runtime}; baseline tests {result.baseline_outcome}")

    identification = await _stage("identification", issue)
    if not isinstance(identification, IssueIdentification):
        return stop("identification", failure_of("identification"))
    if identification.status != "ready":
        return stop("identification", f"identification {identification.status}: {identification.reason}",
                    identification=identification)
    ready("identification", lambda: "issue located in the source")

    try:
        planning_input = TestPlanningInput(scope=issue.scope, identification=identification,
                                           source_files=source_files, environment=environment)
    except ValueError as exc:
        return stop("planning", f"planning input refused: {exc}"[:2048], identification=identification)
    plan = await _stage("planning", planning_input)
    if plan is None:
        return stop("planning", failure_of("planning"), identification=identification)
    if not isinstance(plan, ReadyTestPlan):
        return stop("planning", f"plan unsupported: {plan.missing_capability}", identification=identification)
    ready("planning", lambda: f"control {plan.control.test_id}; security {plan.security.test_id}")

    try:
        authoring_input = TestAuthoringInput(plan=plan, source_files=source_files, environment=environment)
    except ValueError as exc:
        return stop("authoring", f"authoring input refused: {exc}"[:2048], identification=identification, plan=plan)
    patch = await _stage("authoring", authoring_input)
    if patch is None:
        return stop("authoring", failure_of("authoring"), identification=identification, plan=plan)
    if not isinstance(patch, TestPatch):
        return stop("authoring", f"authoring blocked at {patch.layer}: {patch.reason}",
                    identification=identification, plan=plan)
    ready("authoring", lambda: f"{len(patch.files)} test file(s) written")

    report(lambda: StageStarted("execution"))
    try:
        expected = observation_plan(plan, patch)
        frozen = freeze(patch, environment.approved_test_paths)
    except ValueError as exc:
        return stop("execution", f"patch not frozen: {exc}"[:2048], identification=identification, plan=plan,
                    patch=patch)
    executions = []
    try:
        recorders = environment.witness_facilities if case.witness_from_recorders else ()
        request, unrequested = witness_request(identification, case.witness_envelope, plan.security.witness,
                                               recorders), ()
    except ValueError as exc:
        # No approved envelope covers the identified target: run without a witness and say so.
        request, unrequested = None, (f"no witness requested: {exc}"[:512],)
    for revision in ("baseline", "candidate"):
        operation, observed, failure = new_operation(), None, None
        report(lambda: RevisionStarted(revision))
        try:
            observed = await execute(revision, frozen, control_test_id=plan.control.test_id,
                                     security_test_id=plan.security.test_id,
                                     discovery_command=plan.discovery_command, operation=operation,
                                     witness=request)
        except Exception as exc:
            # A refused request (bad ids or patch) dispatched nothing; it is recorded, never retried.
            failure = exc
        executions.append(FrozenExecution(revision, operation, observed, failure))
        report(lambda: RevisionEnded(revision, "ran", outcomes(observed)) if observed is not None
               else RevisionEnded(revision, "refused", clean(f"{type(failure).__name__}: {failure}")))
    done = {"identification": identification, "plan": plan, "patch": patch, "observation_plan": expected,
            "executions": tuple(executions)}
    problems = []
    for e in executions:
        if e.observed is None:
            problems.append(f"{e.revision} run refused: {e.failure}")
        elif e.observed.operation != str(e.operation) or e.observed.patch_sha256 != frozen.sha256:
            problems.append(f"{e.revision} runner returned another operation or patch")
        elif (e.observed.workspace is not None
              and e.observed.workspace.source.sha256 != case.revision_sources[e.revision]):
            problems.append(f"{e.revision} workspace source is not the {e.revision} revision")
    if problems:
        return stop("execution", "; ".join(problems)[:2048], **done)

    ready("execution", lambda: "both revisions ran")
    runs = {e.revision: (e.observed,) for e in executions}
    def witness_of(e):
        if not request:
            return WitnessEvidence(None, None, "no witness was requested or captured for this run")
        # An absence counts as the planned safe behavior only on the candidate until SPEC-0040's control
        # calibration lands: an uncalibrated baseline absence (a vacuous payload) must not be not_reproduced.
        planned = plan.security_expectation.safe_behavior if e.revision == "candidate" else None
        return witness_evidence(e.observed.witness, request, plan.security.test_id, planned_safe_behavior=planned)
    witnesses = {e.revision: witness_of(e) for e in executions}
    done["witnesses"] = tuple(witnesses.values())

    def gate_run(revision):
        found = witnesses[revision]
        return run_evidence(runs[revision][0], environment=identity, witness=found.witness,
                            sandbox_events=found.sandbox_events)
    evidence = AssessmentEvidence(plan=expected, baseline=(gate_run("baseline"),), candidate=(gate_run("candidate"),))
    gate = assess(evidence)
    report(lambda: GateDecided(verdict(gate.permitted)))
    limitations = UNOBSERVED[:2] + provenance + selected + unrequested + tuple(f"{revision} witness not admitted: {found.reason}"
                                     for revision, found in witnesses.items() if found.witness is None) + tuple(
        f"{e.revision} workspace cleanup {e.observed.cleanup}" for e in executions if e.observed.cleanup != "confirmed")
    try:
        assessment_input = AssessmentInput(scope=issue.scope, evidence=evidence,
                                           items=evidence_items(expected, patch, identity, runs, admitted={
                                               revision for revision, found in witnesses.items()
                                               if found.witness is not None}))
    except ValueError as exc:
        return stop("assessment", f"assessment input refused: {exc}"[:2048], gate=gate, limitations=limitations,
                    **done)
    assessment = await _stage("assessment", assessment_input)
    if not isinstance(assessment, EvidenceAssessment):
        return stop("assessment", failure_of("assessment"), gate=gate, limitations=limitations, **done)
    ready("assessment", lambda: f"{verdict(assessment.disposition)}; proposal "
                        f"{'admitted' if assessment.admission.admitted else 'rejected'}")
    report(lambda: RunEnded(None, "complete", verdict(assessment.disposition)))
    return DirectRun(stopped_at=None, reason="complete", attempts=tuple(attempts), gate=gate, assessment=assessment,
                     limitations=limitations, runtime=runtime, environment=prepared, **done)


def verdict(disposition) -> str:
    return f"execution {disposition.execution}, finding {disposition.finding}, fix {disposition.fix}"


def outcomes(observed: NativeTestRun) -> str:
    """One revision run in a line: each executed test's outcome, or the layer that stopped it."""
    if observed.failure_layer is not None:
        return clean(f"{observed.failure_layer} failed: {observed.detail}")
    cases = observed.execution.cases if observed.execution else ()
    return clean("; ".join(f"{c.test_id.rsplit('::', 1)[-1]} {c.outcome}" for c in cases) or observed.detail)
