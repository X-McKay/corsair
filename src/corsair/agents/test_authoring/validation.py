"""Trusted finalization: the patch is assembled from this run's own writes and runs; the model restates no file or outcome."""

from pydantic_ai import CallToolsNode, ModelRetry, RunContext
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.result import FinalResult
from pydantic_graph import End

from .admission import self_observation
from .contracts import AuthoringDraft, AuthoringResult, BlockedAuthoring, PatchedFile, TestPatch
from .dependencies import AuthoringDependencies
from .static import assertion_lines
from .tools._history import (RUN_TOOL, WRITE_TOOL, admission_spent, approved_patch, current_files, development_runs,
                             refused_writes)
from .tools._preparation import withdrawal


def _patched(ctx: RunContext[AuthoringDependencies]) -> tuple[PatchedFile, ...]:
    return tuple(PatchedFile(path=path, content=content) for path, content in sorted(current_files(ctx).items()))


async def finalize_authoring(ctx: RunContext[AuthoringDependencies], result: AuthoringDraft) -> AuthoringResult:
    """Assemble the patch from this run's own writes and runs; the model restates no file or outcome."""
    inputs = ctx.deps.inputs
    plan = inputs.plan
    files = current_files(ctx)
    runs = tuple(development_runs(ctx))
    patched = _patched(ctx)
    if admission_spent(ctx):
        # Trusted code names the layer: the author kept writing what the admission check refuses.
        return BlockedAuthoring(status="blocked", layer="admission", reason=refused_writes(ctx)[-1].reason[:512],
                                files=patched, dev_runs=runs)
    if result.status == "blocked":
        return BlockedAuthoring(status="blocked", layer=result.layer, reason=result.reason, files=patched,
                                dev_runs=runs)
    executed = [run for run in runs if run.status != "not_run"]
    if not files or not executed:
        raise ModelRetry("a patch needs written test files and at least one run_tests call in this run")
    final = executed[-1]
    if final.status == "workspace_failure":
        raise ModelRetry("the last run was a workspace failure: the workspace refused or failed before any test ran, "
                         "which no test edit can fix; return blocked with layer sandbox when the errors show a sandbox "
                         "refusal, otherwise unknown, and quote the observed reason")
    if any(self_observation(content) for content in files.values()):
        raise RuntimeError("an admitted write contains a refused construct")  # write_test_file refuses these
    patch = approved_patch(files, inputs.environment.approved_test_paths)
    if final.patch_sha256 != patch.sha256:
        raise ModelRetry("the last run_tests call must cover the final files; call run_tests after the last write, "
                         "or return blocked when run_tests is no longer offered")
    if {plan.control.test_path, plan.security.test_path} - set(files):
        raise ModelRetry("both planned test paths must be written")
    if final.status != "discovered" or set(final.discovered_test_ids) != {plan.control.test_id, plan.security.test_id}:
        raise ModelRetry("the final run must discover exactly the two planned tests; otherwise return blocked")
    if final.control is None or final.control.outcome != "passed":
        raise ModelRetry("the final run's control must pass; otherwise return blocked")
    if final.security is None or (final.security != "withheld" and final.security.outcome in ("error", "skipped")):
        raise ModelRetry("the final run's security test must run without a setup error or skip; otherwise return blocked")
    try:
        assertion_lines(files[plan.control.test_path], plan.control.test_id)
        security_lines = assertion_lines(files[plan.security.test_path], plan.security.test_id)
    except ValueError as exc:
        raise ModelRetry(str(exc)) from exc
    if not set(result.security_assertion_lines) <= set(security_lines):
        raise ModelRetry(f"security_assertion_lines must be assertion lines of {plan.security.test_id}: {list(security_lines)}")
    return TestPatch(status="patch", files=patched, control_test_id=plan.control.test_id,
                     security_test_id=plan.security.test_id, discovery_command=plan.discovery_command,
                     run_command=final.run_command, patch_sha256=patch.sha256,
                     security_assertion_lines=tuple(sorted(set(result.security_assertion_lines))), dev_runs=runs,
                     limitations=result.limitations)


async def end_on_withdrawn_call(ctx: RunContext[AuthoringDependencies], *, node, error: Exception):
    """A call to a withdrawn write or run ends the stage blocked instead of failing it.

    Withdrawn tools are no longer offered, so PydanticAI refuses such a call as an unknown tool and, with tool
    retries at 0, ends the run on UnexpectedModelBehavior. Trusted code names the reason; the layer is admission
    when the refusals are spent and otherwise unknown, since no run observed what an edit would have changed.
    """
    why = withdrawal(ctx)
    called = [name for name in (WRITE_TOOL, RUN_TOOL) if f"'{name}'" in str(error)]
    if not (why and called and isinstance(error, UnexpectedModelBehavior) and isinstance(node, CallToolsNode)):
        raise error
    reason = f"the author called {called[0]} after it was withdrawn: {why}"
    blocked = BlockedAuthoring(status="blocked", layer="admission" if admission_spent(ctx) else "unknown",
                               reason=reason[:2048], files=_patched(ctx), dev_runs=tuple(development_runs(ctx)))
    return End(FinalResult(blocked))
