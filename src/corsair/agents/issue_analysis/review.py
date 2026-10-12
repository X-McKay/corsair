"""Isolated, read-only evidence review of a completed issue analysis."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.capabilities import Capability, Instrumentation
from pydantic_ai.messages import ModelRequest, ToolReturnPart
from pydantic_ai.models import Model
from pydantic_ai.models.instrumented import InstrumentationSettings

from .contracts import IssueAnalysis, IssueAnalysisInput, SourceExcerpt, SourceRead, SourceReference
from .review_contracts import ReviewDraft, ReviewFinding, ReviewReport
from .tools import FixtureDependencies, source_tools


_SKILL_PATH = Path(__file__).parent / "skills" / "review-evidence" / "SKILL.md"
REVIEW_SKILL_TEXT = _SKILL_PATH.read_text(encoding="utf-8")
REVIEW_SKILL_SHA256 = sha256(_SKILL_PATH.read_bytes()).hexdigest()
REVIEW_PROMPT_VERSION = "issue-evidence-review-v2"


@dataclass(frozen=True)
class ReviewDependencies(FixtureDependencies):
    analysis: IssueAnalysis


def review_prompt(inputs: IssueAnalysisInput, analysis: IssueAnalysis) -> str:
    """Give the reviewer the issue, inventory, and analysis, never hidden source or oracle labels."""
    if inputs.scope != analysis.scope:
        raise ValueError("analysis scope differs from the review input scope")
    inventory = ", ".join(
        f"{source.path} (saved-file inclusive lines 1..{len(source.content.splitlines())})"
        for source in inputs.source_files
    )
    return (inputs.model_dump_json(exclude={"source_files", "fixture_id"})
            + "\nSaved source inventory: " + inventory
            + "\nCompleted analysis to review: "
            + analysis.model_dump_json(exclude={"citations": {"__all__": {"quote"}}}))


def create_evidence_reviewer(model: Model, *, output_retries: int = 1) -> Agent[ReviewDependencies, ReviewReport]:
    """Build the separate reviewer; no workflow or provider is selected here."""
    if not isinstance(model, Model):
        raise TypeError("an explicit PydanticAI Model instance is required")

    async def finalize_review(ctx: RunContext[ReviewDependencies], draft: ReviewDraft) -> ReviewReport:
        if draft.scope != ctx.deps.inputs.scope or draft.scope != ctx.deps.analysis.scope:
            raise ModelRetry("review scope must match the issue and analysis scopes")
        if ctx.deps.analysis.status == "ready" and draft.assessment == "supported" and not draft.condition_audit:
            raise ModelRetry("supporting a ready hypothesis requires a necessary-condition audit")
        reads: list[SourceRead] = []
        for message in ctx.messages:
            if isinstance(message, ModelRequest) and message.run_id == ctx.run_id:
                for part in message.parts:
                    if (isinstance(part, ToolReturnPart) and part.tool_name == "read_source"
                            and part.outcome == "success"):
                        reads.append(SourceRead.model_validate(part.content))
        cited = bool(draft.citations or any(finding.citations for finding in draft.findings))
        if ctx.deps.inputs.source_files and draft.assessment != "insufficient_evidence" and not cited:
            raise ModelRetry("conclusive review of listed source requires a current-run source citation")
        if draft.assessment == "supported":
            for candidate_citation in ctx.deps.analysis.citations:
                try:
                    saved = ctx.deps.read_source(candidate_citation.path, candidate_citation.start_line,
                                                 candidate_citation.end_line)
                except ValueError as exc:
                    raise ModelRetry("candidate analysis citation is absent from immutable saved source") from exc
                if saved.quote != candidate_citation.quote:
                    raise ModelRetry("candidate analysis citation does not match immutable saved source")

        def resolve(reference: SourceReference) -> SourceExcerpt:
            if not any(read.path == reference.path and read.start_line <= reference.start_line
                       and reference.end_line <= read.end_line for read in reads):
                raise ModelRetry("review citation must reference source read during this review run")
            try:
                return ctx.deps.read_source(reference.path, reference.start_line, reference.end_line)
            except ValueError as exc:
                raise ModelRetry(str(exc)) from exc

        return ReviewReport(
            assessment=draft.assessment, scope=draft.scope,
            findings=tuple(ReviewFinding(field_path=finding.field_path, problem=finding.problem,
                                         citations=tuple(resolve(ref) for ref in finding.citations))
                           for finding in draft.findings),
            citations=tuple(resolve(ref) for ref in draft.citations),
            condition_audit=draft.condition_audit,
            limitations=draft.limitations,
        )

    return Agent[ReviewDependencies, ReviewReport](
        model, name="issue_evidence_review", deps_type=ReviewDependencies, output_type=finalize_review,
        instructions="Review the completed analysis only at the supplied scope. Follow the review-evidence skill. "
                     "Use only read_source; do not rewrite the analysis, execute code, or verify a finding or fix.",
        retries={"tools": 0, "output": output_retries},
        capabilities=[Capability(id="review-evidence", instructions=REVIEW_SKILL_TEXT,
                                 toolsets=[source_tools()]),
                      Instrumentation(settings=InstrumentationSettings(include_content=False))],
    )
