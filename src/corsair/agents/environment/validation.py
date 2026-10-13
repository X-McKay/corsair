"""Trusted finalization: admit an environment draft only against this run's reads and ledger."""

from pydantic import TypeAdapter
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ModelRequest, ToolReturnPart

from corsair.agents.issue_analysis.contracts import SourceRead, SourceReference

from .contracts import EnvironmentDraft, EnvironmentResult, ReadyEnvironmentDraft
from .dependencies import EnvironmentDependencies
from .frameworks import FRAMEWORKS, file_matches, project_tests
from .tools.read_source import READ_SOURCE_TOOL
from .tools.run_setup_command import RUN_SETUP_COMMAND_TOOL, SetupRun

_RESULT = TypeAdapter(EnvironmentResult)


def _current(ctx: RunContext[EnvironmentDependencies], tool: str) -> list:
    return [part.content for message in ctx.messages if isinstance(message, ModelRequest) and message.run_id == ctx.run_id
            for part in message.parts if isinstance(part, ToolReturnPart) and part.tool_name == tool and part.outcome == "success"]


def _covered(reads: list[SourceRead], reference: SourceReference) -> bool:
    return any(r.path == reference.path and r.start_line <= reference.start_line and reference.end_line <= r.end_line
               for r in reads)


def _subsequence(observed: list[tuple[str, ...]], required: list[tuple[str, ...]]) -> list[int] | None:
    positions, start = [], 0
    for command in required:
        try:
            start = observed.index(command, start)
        except ValueError:
            return None
        positions.append(start); start += 1
    return positions


async def finalize_environment(ctx: RunContext[EnvironmentDependencies], draft: EnvironmentDraft) -> EnvironmentResult:
    deps = ctx.deps
    reads = [SourceRead.model_validate(c) for c in _current(ctx, READ_SOURCE_TOOL)]
    runs = {r.run_id: r for r in (SetupRun.model_validate(c) for c in _current(ctx, RUN_SETUP_COMMAND_TOOL))}
    records = {r.run_id: r for r in deps.ledger.records}
    if set(runs) - set(records):
        raise ModelRetry("command results must come from this run's ledger")
    citations = [step.source for step in draft.recipe] if isinstance(draft, ReadyEnvironmentDraft) else list(draft.citations)
    for reference in citations:
        if not _covered(reads, reference):
            raise ModelRetry(f"{reference.path}:{reference.start_line}-{reference.end_line} must be covered by a successful read_source in this run")
    quoted = lambda ref: deps.read_source(ref.path, ref.start_line, ref.end_line).model_dump()
    values = draft.model_dump() | {"receipts": [r.model_dump() for r in deps.ledger.records]}
    if draft.status == "ready":
        if deps.ledger.halted or deps.ledger.pending_correction is not None:
            raise ModelRetry("setup has an unresolved command failure or execution halt; report blocked, not ready")
        if draft.toolchain_id != deps.toolchain_id:
            raise ModelRetry("ready requires the preparation sandbox's toolchain")
        framework = FRAMEWORKS.get(draft.framework)
        if framework is None:
            raise ModelRetry(f"framework must be one of {sorted(FRAMEWORKS)}; otherwise report unsupported")
        smoke = next((t for t in deps.inputs.smoke_tests if t.path == draft.baseline_test_path), None)
        if smoke is not None and (smoke.framework != draft.framework or smoke.test_id != draft.baseline_test_id):
            raise ModelRetry(f"the supplied smoke test is the {smoke.framework} test {smoke.test_id}; use it exactly or a project test")
        if not file_matches(draft.framework, draft.baseline_test_id, draft.baseline_test_path):
            raise ModelRetry("baseline_test_path must be exactly the file the native baseline_test_id names")
        if not framework.targets(tuple(draft.baseline_test_command), draft.baseline_test_id):
            raise ModelRetry("baseline_test_command must target exactly baseline_test_id")
        succeeded = [rid for rid in sorted(runs) if records[rid].exit_code == 0 and records[rid].execution_error is None
                     and records[rid].delivery == "acknowledged" and records[rid].completion == "terminal_observed"]
        required = [s.command for s in draft.recipe] + [draft.build_command, draft.discovery_command, draft.baseline_test_command]
        positions = _subsequence([records[rid].command for rid in succeeded], required)
        if positions is None:
            raise ModelRetry("recipe, build, discovery and baseline test commands must each have succeeded in this order in this run")
        discovery, baseline = succeeded[positions[-2]], succeeded[positions[-1]]
        if draft.baseline_test_id.encode() not in deps.ledger.outputs[discovery][0]:
            raise ModelRetry("baseline_test_id must appear in the discovery command's output")
        if smoke is not None and (others := project_tests(draft.framework, smoke, deps.ledger.outputs[discovery][0])):
            raise ModelRetry(f"discovery listed project tests ({', '.join(others[:3])}); use one of them as the baseline, "
                             "not the smoke test")
        if not framework.passed(deps.ledger.outputs[baseline][0]):
            raise ModelRetry("the baseline run must report exactly one passed test, with nothing skipped, xfailed or errored")
        if set(draft.approved_test_paths) & {s.path for s in (*deps.inputs.source_files, *deps.inputs.smoke_tests)}:
            raise ModelRetry("approved_test_paths must not name saved source files or the smoke test")
        toolchain = next(t for t in deps.inputs.toolchains if t.toolchain_id == deps.toolchain_id)
        values |= {"recipe": [s.model_dump() | {"source": quoted(s.source)} for s in draft.recipe],
                   "toolchain_image": toolchain.image, "language": toolchain.language, "runtime": toolchain.runtime, "baseline_outcome": "passed", "scratch_location": deps.scratch_location,
                   "baseline_basis": "project_test" if smoke is None else "operator_smoke"}
    else:
        if draft.status == "unsupported" and (deps.ledger.halted or deps.ledger.pending_correction is not None):
            raise ModelRetry("setup halted on an observed failure; report blocked and cite its run, not unsupported")
        values["citations"] = [quoted(c) for c in draft.citations]
        if draft.status == "blocked":
            values["diagnostics"] = [d.model_dump() for d in deps.ledger.diagnostics]
            if set(draft.run_ids) - set(runs):
                raise ModelRetry("blocked run_ids must name commands run in this run")
            failed = [rid for rid in draft.run_ids if records[rid].exit_code != 0 or records[rid].execution_error
                      or records[rid].delivery != "acknowledged" or records[rid].completion != "terminal_observed"]
            if draft.run_ids and not failed:
                raise ModelRetry("blocked evidence must cite at least one failed command")
            if not draft.run_ids and any(r.exit_code != 0 or r.execution_error or r.delivery != "acknowledged"
                                        or r.completion != "terminal_observed" for r in records.values()):
                raise ModelRetry("cite the failed command run_ids; do not hide an observed failure behind a generic halt")
            if not draft.run_ids and (draft.layer not in ("sandbox", "unknown") or not (
                    deps.ledger.halted or len(deps.ledger.records) >= deps.budget.max_commands)):
                raise ModelRetry("blocked without cited runs requires a halt or an exhausted budget and layer sandbox or unknown")
            quoted_from = [part for rid in failed for part in (*deps.ledger.outputs[rid], (records[rid].execution_error or "").encode())]
            if draft.run_ids and not any(draft.evidence.encode() in part for part in quoted_from):
                raise ModelRetry("blocked evidence must be an exact excerpt of a failed cited run's output or execution error")
    return _RESULT.validate_python(values)
