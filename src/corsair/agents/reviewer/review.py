"""The Reviewer's input rendering and the code that turns its answer into a ``contracts.Validity``.

The review input is built only from the finding, the plan and the frozen patch; ``review`` has no parameter that
could carry an execution result, and the revision label is kept out of the prompt so the review cannot lean on
which revision it is reading. ``valid`` is computed here as all four checks, never taken from the model, and
every citation must resolve to real lines, whose text code fills in.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import ModelRetry, RunContext

from ...contracts import Case, Citation, FrozenPatch, ProbeDraft, ProbePlan, ProbeValidity, Runtime
from ..probing.source import numbered, source_lines

CHECKS = ("calls_real_target", "exercises_condition", "assertion_relevant", "doubles_only_dependencies")


class ReviewDeps(BaseModel):
    """What citation checks need: the revision's tree and the two frozen drafts by role. Nothing else."""

    model_config = ConfigDict(frozen=True)

    source_root: Path
    drafts: dict[str, ProbeDraft] = Field(description="role -> frozen draft")


class CitedLines(BaseModel):
    path: str = Field(description="A source path or one of the two test files")
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


class ProbeJudgement(BaseModel):
    calls_real_target: bool
    exercises_condition: bool
    assertion_relevant: bool
    doubles_only_dependencies: bool
    defects: list[str] = Field(default=[], max_length=16, description="One line per defect found")
    citations: list[CitedLines] = Field(default=[], max_length=16)


class ReviewAnswer(BaseModel):
    control: ProbeJudgement
    exploit: ProbeJudgement


def _probe_block(draft: ProbeDraft) -> str:
    return (f"--- {draft.role} probe: file {draft.test_file}, test {draft.test_name} ---\n"
            f"{numbered(draft.source)}")


def render_prompt(case: Case, plan: ProbePlan, patch: FrozenPatch, runtime: Runtime | None = None) -> str:
    finding = case.finding
    lines = ["Review the two frozen probe tests below."]
    if runtime is not None:
        lines.append(f"Test framework: {runtime.framework}. Load the skill `{runtime.skill}` if it is offered; "
                     "judge marker placement by its pattern.")
    lines += [
        "Reported finding (untrusted):",
        f"  title: {finding.title}",
        f"  description: {finding.description or '-'}",
        f"  location: {finding.file_path or '-'}{':' + str(finding.start_line) if finding.start_line else ''}",
        f"  symbol: {finding.symbol or '-'}",
        f"  weakness: {finding.cwe or '-'}",
        f"Plan target: {plan.target}",
        f"Plan hypothesis: {plan.hypothesis}",
    ]
    for brief in (plan.control, plan.exploit):
        if brief is not None:
            lines += [f"Planned {brief.role} probe: seam: {brief.seam}", f"  input: {brief.input_description}",
                      f"  property: {brief.property_to_assert}",
                      *([f"  safe_observation: {brief.safe_observation}"] if brief.safe_observation else []),
                      f"  dependencies that may be doubled: {brief.doubles or 'none named'}"]
    lines += ["", _probe_block(patch.control), "", _probe_block(patch.exploit)]
    return "\n".join(lines)


def _citation(deps: ReviewDeps, cited: CitedLines) -> Citation | str:
    drafts = {draft.test_file: draft.source.splitlines() for draft in deps.drafts.values()}
    lines = drafts.get(cited.path) or source_lines(deps.source_root, cited.path)
    if lines is None:
        return f"citation path {cited.path!r} is neither a test file nor a readable source file"
    if cited.end_line < cited.start_line or cited.end_line > len(lines):
        return f"citation {cited.path}:{cited.start_line}-{cited.end_line} is outside the file's {len(lines)} lines"
    quote = "\n".join(lines[cited.start_line - 1:cited.end_line])[:2_000]
    return Citation(path=cited.path, start_line=cited.start_line, end_line=cited.end_line, quote=quote)


def judge(deps: ReviewDeps, role: Literal["control", "exploit"], answer: ProbeJudgement
          ) -> tuple[ProbeValidity | None, list[str]]:
    problems, citations = [], []
    for cited in answer.citations:
        resolved = _citation(deps, cited)
        if isinstance(resolved, str):
            problems.append(f"{role}: {resolved}")
        else:
            citations.append(resolved)
    checks = {name: getattr(answer, name) for name in CHECKS}
    if not all(checks.values()) and not answer.defects:
        problems.append(f"{role}: every false check needs a defect naming why")
    if all(checks.values()):
        test_files = {draft.test_file for draft in deps.drafts.values()}
        test_file = deps.drafts[role].test_file
        if not any(c.path == test_file for c in citations):
            problems.append(f"{role}: a valid judgement must cite the lines of {test_file} that call and assert")
        if not any(c.path not in test_files for c in citations):
            problems.append(f"{role}: a valid judgement must cite the target's definition in the source")
    if problems:
        return None, problems
    defects = tuple(defect.strip()[:500] for defect in answer.defects if defect.strip())
    return ProbeValidity(role=role, valid=all(checks.values()), defects=defects, citations=tuple(citations),
                         **checks), []


async def finalize_review(ctx: RunContext[ReviewDeps], answer: ReviewAnswer) -> tuple[ProbeValidity, ProbeValidity]:
    control, control_problems = judge(ctx.deps, "control", answer.control)
    exploit, exploit_problems = judge(ctx.deps, "exploit", answer.exploit)
    if control is None or exploit is None:
        raise ModelRetry("; ".join(control_problems + exploit_problems))
    return control, exploit


def not_reviewed(role: Literal["control", "exploit"], status: str) -> ProbeValidity:
    """A review that did not complete is negative, never assumed valid."""
    return ProbeValidity(role=role, valid=False, calls_real_target=False, exercises_condition=False,
                         assertion_relevant=False, doubles_only_dependencies=False,
                         defects=(f"review not completed: {status}",))


__all__ = ["CHECKS", "ReviewAnswer", "ReviewDeps", "finalize_review", "judge", "not_reviewed", "render_prompt"]
