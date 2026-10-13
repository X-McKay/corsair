"""run_tests: the current patch in a fresh development sandbox; discovery, control outcome, withheld security verdict."""

from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5

from pydantic_ai import RunContext
from pydantic_ai.messages import ModelResponse, ToolCallPart

from corsair.nodes.witness import witness_evidence
from corsair.ports.test_runner import FailureDetail, NativeTestRun, TestCaseResult, WitnessRequest

from ..contracts import DevelopmentOutcome, DevelopmentRun
from ..dependencies import AuthoringDependencies
from ._history import RUN_TOOL, approved_patch, current_files, dispatched_runs

__all__ = ["RUN_TOOL", "run_tests", "summarize"]
EXCERPT = 4096


def _outcome(case: TestCaseResult | None) -> DevelopmentOutcome | None:
    if case is None:
        return None
    failure: FailureDetail | None = case.failure
    return DevelopmentOutcome(outcome=case.outcome, failure_type=failure.type if failure else None,
                              failure_path=failure.path if failure else None,
                              failure_line=failure.line if failure else None,
                              message=(failure.message if failure else "")[:EXCERPT])


def _contradicts(observed: NativeTestRun, request: WitnessRequest | None, security: TestCaseResult | None) -> bool:
    """The security test passed while the admitted witness shows the target performed the planned effect."""
    if request is None or security is None or security.outcome != "passed":
        return False
    found = witness_evidence(observed.witness, request, security.test_id).witness
    return found is not None and found.path_reached is True and found.effect == "observed"


def _control_reached(observed: NativeTestRun, request: WitnessRequest | None, control: TestCaseResult | None) -> bool | None:
    """Whether the operator witness saw the control test call the identified target; None when it cannot say."""
    if request is None or control is None:
        return None
    found = witness_evidence(observed.witness, request, control.test_id).witness
    return None if found is None else found.path_reached


def summarize(number: int, observed: NativeTestRun, *, control_id: str, security_id: str,
              reveal_security: bool, planned_failure: str | None = None,
              witness: WitnessRequest | None = None) -> DevelopmentRun:
    """What the author may see: discovery, compile/collection errors and the control; never the security verdict by default.

    A security failure of another type than ``planned_failure`` is shown: the test broke before its planned
    assertion (a fixture or call error), which is a test-code problem on any revision, not a verdict. A pass
    while the operator witness recorded the planned effect is shown too: the assertion cannot detect the effect,
    whichever revision is vulnerable (the gate's ``security_passed_with_effect``).
    """
    discovery, execution = observed.discovery, observed.execution
    status: str = {"workspace": "workspace_failure", "discovery": "collection_error",
                   "execution": "execution_failure", "report": "report_failure", None: "discovered"}[observed.failure_layer]
    if observed.failure_layer == "discovery" and discovery is not None and discovery.status == "execution_failure":
        status = "execution_failure"
    cases = {case.test_id: case for case in (execution.cases if execution else ())}
    security = cases.get(security_id)
    if security is not None and not reveal_security:
        # A setup error or skip means the body did not run validly and says nothing about the planned
        # assertion; only the pass/fail verdict is withheld.
        broken = security.outcome == "failed" and planned_failure is not None and (
            security.failure is None or security.failure.type != planned_failure)
        contradicted = _contradicts(observed, witness, security)
        security_view = (_outcome(security) if security.outcome in ("error", "skipped") or broken or contradicted
                         else "withheld")
    else:
        security_view = _outcome(security)
    errors = (discovery.errors if discovery else "") or (execution.detail if execution else "") or observed.detail
    return DevelopmentRun(
        run=number, operation=observed.operation, patch_sha256=observed.patch_sha256, status=status,
        discovered_test_ids=discovery.test_ids[:64] if discovery else (), errors=errors[:EXCERPT],
        control=_outcome(cases.get(control_id)), security=security_view,
        security_contradicts_witness=_contradicts(observed, witness, security),
        control_reached_target=_control_reached(observed, witness, cases.get(control_id)),
        run_command=execution.command if execution else (), cleanup=observed.cleanup)


def run_tests(ctx: RunContext[AuthoringDependencies]) -> DevelopmentRun:
    """Apply the current patch to a fresh copy of the baseline source in the development sandbox, run native discovery and, when exactly the two planned tests are found, execute them once.

    Returns discovered test ids, collection or compile errors and the control outcome. The security test's pass/fail outcome is withheld; a setup error or skip is shown. Every call counts against an operator run budget; only the first call in one response runs.
    """
    deps = ctx.deps
    plan = deps.inputs.plan
    # Reserve against every run_tests call dispatched in this run, including others in the same
    # model response whose returns are not yet in history; each call gets its own operation.
    dispatched = dispatched_runs(ctx)
    if dispatched.count(ctx.tool_call_id) != 1:
        raise RuntimeError("run_tests call id must identify exactly one dispatched call in this run")
    number = dispatched.index(ctx.tool_call_id) + 1
    # Calls in one response see the same files, so a later one would repeat the first run's patch blindly,
    # including after a workspace failure with uncertain side effects; only the first runs.
    response = next(message for message in ctx.messages if isinstance(message, ModelResponse)
                    and message.run_id == ctx.run_id and any(isinstance(part, ToolCallPart)
                                                             and part.tool_call_id == ctx.tool_call_id
                                                             for part in message.parts))
    batched = [part.tool_call_id for part in response.parts
               if isinstance(part, ToolCallPart) and part.tool_name == RUN_TOOL]
    files = current_files(ctx)
    if not files or number > deps.budget.dev_runs or batched[0] != ctx.tool_call_id:
        reason = ("no test file has been written" if not files
                  else f"development run budget of {deps.budget.dev_runs} is spent" if number > deps.budget.dev_runs
                  else "only the first run_tests call in one response runs; the files cannot change between them")
        return DevelopmentRun(run=number, operation="", patch_sha256=sha256(b"").hexdigest(), status="not_run",
                              discovered_test_ids=(), errors=reason, control=None, security=None,
                              run_command=(), cleanup="not_required")
    patch = approved_patch(files, deps.inputs.environment.approved_test_paths)
    operation = uuid5(NAMESPACE_URL, f"corsair:test-authoring:{ctx.run_id}:{ctx.tool_call_id}")
    envelope = deps.inputs.witness
    request = (WitnessRequest(envelope.target_path, envelope.target_symbol, envelope.effect_name)
               if envelope is not None else None)
    observed = deps.runner.run(patch, control_test_id=plan.control.test_id,
                               security_test_id=plan.security.test_id,
                               discovery_command=plan.discovery_command, operation=operation,
                               **({"witness": request} if request is not None else {}))
    if observed.operation != str(operation) or observed.patch_sha256 != patch.sha256:
        raise RuntimeError("runner returned an observation for a different operation or patch")
    return summarize(number, observed, control_id=plan.control.test_id, security_id=plan.security.test_id,
                     reveal_security=deps.budget.reveal_security_outcome,
                     planned_failure=plan.security_expectation.failure_type, witness=request)
