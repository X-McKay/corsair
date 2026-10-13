"""Trusted finalization: the patch is assembled from this run's own writes and runs; the model restates no file or outcome."""

from pydantic_ai import ModelRetry, RunContext

from .admission import self_observation
from .contracts import AuthoringDraft, AuthoringResult, BlockedAuthoring, PatchedFile, TestPatch
from .dependencies import AuthoringDependencies
from .static import assertion_lines
from .tools._history import admission_spent, approved_patch, current_files, development_runs, refused_writes


async def finalize_authoring(ctx: RunContext[AuthoringDependencies], result: AuthoringDraft) -> AuthoringResult:
    """Assemble the patch from this run's own writes and runs; the model restates no file or outcome."""
    inputs = ctx.deps.inputs
    plan = inputs.plan
    files = current_files(ctx)
    runs = tuple(development_runs(ctx))
    patched = tuple(PatchedFile(path=path, content=content) for path, content in sorted(files.items()))
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
    planned = plan.security_expectation.failure_type
    if (final.security != "withheld" and final.security.outcome == "failed"
            and final.security.failure_type != planned):
        # Gap 9 (Docker run live-002): an error in the test body before the planned assertion fails the same way on
        # every revision, so the test cannot distinguish them.
        raise ModelRetry(f"the final run's security test failed with {final.security.failure_type or 'an unclassified error'}"
                         f" at line {final.security.failure_line}, not through its planned {planned} assertion; an error"
                         " before the planned assertion cannot distinguish the revisions: fix the observed error and run"
                         " again, or return blocked")
    if final.security_contradicts_witness:
        # Gap 11: the gate would classify this run security_passed_with_effect; nothing the test asserts sees the effect.
        raise ModelRetry("the final run's security test passed although the operator witness recorded the target "
                         f"performing the planned effect on {plan.security.witness.subject}: its assertion cannot detect "
                         "that effect; assert on what the call returned or on fixture state the effect changes, run again, "
                         "or return blocked")
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
