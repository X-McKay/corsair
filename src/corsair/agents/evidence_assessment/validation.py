"""Trusted finalization: citations must come from this run's reads; conclusions need witness items; gates decide."""

from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ModelRequest, ToolReturnPart

from corsair.core.disposition import Disposition, admit, assess

from .contracts import AssessmentInput, EvidenceAssessment, EvidenceRead, ProposedDispositionDraft
from .dependencies import AssessmentDependencies
from .tools.read_evidence import READ_EVIDENCE_TOOL


def _witnesses(inputs: AssessmentInput, revision: str) -> int:
    return sum(item.kind == "witness" and item.revision == revision for item in inputs.items)


def _witness_problem(inputs: AssessmentInput, cited: set[str], revision: str, claim: str, weaker: str) -> str | None:
    """Only a witness item grounds a conclusion; test-process output (JUnit, stdout, receipts) is a claim."""
    runs = getattr(inputs.evidence, revision)
    required = {index for index, run in enumerate(runs) if run.witness is not None}
    covered = {item.run for item in inputs.items
               if item.item_id in cited and item.kind == "witness" and item.revision == revision}
    if required and required <= covered:
        return None
    if missing := required - covered:
        if len(runs) > 1:
            return (f"{claim} must cite a {revision} item of kind witness for each observed run; "
                    f"missing run indexes {sorted(missing)}; test reports and output are claims")
    if not _witnesses(inputs, revision):
        return (f"the inventory has no witness item for the {revision} revision, so {claim} is unsupported; "
                f"propose {weaker} and record the missing witness in limitations")
    return f"{claim} must cite a {revision} item of kind witness; test reports and output are claims"


async def finalize_assessment(ctx: RunContext[AssessmentDependencies],
                              draft: ProposedDispositionDraft) -> EvidenceAssessment:
    inputs = ctx.deps.inputs
    reads = [EvidenceRead.model_validate(part.content)
             for message in ctx.messages if isinstance(message, ModelRequest) and message.run_id == ctx.run_id
             for part in message.parts if isinstance(part, ToolReturnPart)
             and part.tool_name == READ_EVIDENCE_TOOL and part.outcome == "success"]
    observations = (*draft.application_observations, *draft.sandbox_observations, draft.interpretation)
    references = [reference for observation in observations for reference in observation.citations]
    for reference in references:
        if not any(read.item_id == reference.item_id and read.start_line <= reference.start_line
                   and reference.end_line <= read.end_line for read in reads):
            raise ModelRetry("every citation must be covered by a successful read_evidence in this run")
    cited = {reference.item_id for reference in references}
    problems = []
    if draft.finding in ("reproduced", "not_reproduced"):
        problems.append(_witness_problem(inputs, cited, "baseline", f"finding {draft.finding}",
                                         "finding inconclusive"))
    if draft.fix == "verified":
        problems += [_witness_problem(inputs, cited, revision, "fix verified", "fix not_verified")
                     for revision in ("baseline", "candidate")]
    if problems := [problem for problem in problems if problem]:
        raise ModelRetry("; ".join(dict.fromkeys(problems)))

    def quoted(observation):
        return {"statement": observation.statement, "citations": [
            ctx.deps.read_evidence(c.item_id, c.start_line, c.end_line).model_dump()
            for c in observation.citations]}

    proposal = Disposition(execution=draft.execution, finding=draft.finding, fix=draft.fix)
    result = assess(inputs.evidence)
    return EvidenceAssessment.model_validate(draft.model_dump() | {
        "application_observations": [quoted(o) for o in draft.application_observations],
        "sandbox_observations": [quoted(o) for o in draft.sandbox_observations],
        "interpretation": quoted(draft.interpretation),
        "admission": admit(proposal, result), "gate_limitations": result.limitations,
    })
