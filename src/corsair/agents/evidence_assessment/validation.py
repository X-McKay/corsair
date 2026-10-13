"""Bind independent test review and cited observations to frozen inputs; deterministic gates decide."""

from hashlib import sha256
import json

from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ModelRequest, ToolReturnPart

from corsair.core.disposition import Disposition, TestValidity, admit, assess

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
    references = [reference for observation in (*observations, *(review.rationale for review in draft.validity_reviews))
                  for reference in observation.citations]
    for reference in references:
        if not any(read.item_id == reference.item_id and read.start_line <= reference.start_line
                   and reference.end_line <= read.end_line for read in reads):
            raise ModelRetry("every citation must be covered by a successful read_evidence in this run")
    cited = {reference.item_id for reference in references}
    problems = []
    if inputs.plan.observation_mode == "effect_witness" and draft.finding in ("reproduced", "not_reproduced"):
        problems.append(_witness_problem(inputs, cited, "baseline", f"finding {draft.finding}",
                                         "finding inconclusive"))
    if inputs.plan.observation_mode == "effect_witness" and draft.fix == "verified":
        problems += [_witness_problem(inputs, cited, revision, "fix verified", "fix not_verified")
                     for revision in ("baseline", "candidate")]
    if problems := [problem for problem in problems if problem]:
        raise ModelRetry("; ".join(dict.fromkeys(problems)))

    def quoted(observation):
        return {"statement": observation.statement, "citations": [
            ctx.deps.read_evidence(c.item_id, c.start_line, c.end_line).model_dump()
            for c in observation.citations]}

    proposal = Disposition(execution=draft.execution, finding=draft.finding, fix=draft.fix)
    evidence = inputs.evidence
    reviews = []
    if inputs.plan.observation_mode == "unit_test":
        if len({review.revision for review in draft.validity_reviews}) != len(draft.validity_reviews):
            raise ModelRetry("provide at most one independent validity review per revision")
        for review in draft.validity_reviews:
            runs = getattr(evidence, review.revision)
            if not runs:
                raise ModelRetry("validity review names an absent revision")
            relevant_items = [item for item in inputs.items if item.kind in ("plan", "patch")
                              or (item.kind == "source" and item.revision == review.revision)]
            if (all((review.source_linked, review.condition_exercised,
                     review.assertions_relevant, review.dependency_scope_valid))
                    and any(not item.complete for item in relevant_items)):
                raise ModelRetry("incomplete source, patch or plan evidence cannot support affirmative test validity; "
                                 "mark unsupported conclusions false and report the missing evidence")
            review_items = [item for item in inputs.items
                            if item.item_id in {c.item_id for c in review.rationale.citations}]
            if not all(any(item.kind == kind and (kind != "source" or item.revision == review.revision)
                           for item in review_items) for kind in ("source", "patch", "plan")):
                raise ModelRetry("each validity review must cite read source for its revision, frozen patch and plan")
            source_identities = {run.source_sha256 for run in runs}
            cited_sources = [item for item in review_items if item.kind == "source"]
            if (None in source_identities or len(source_identities) != 1
                    or any(item.revision != review.revision or item.source_sha256 not in source_identities
                           for item in cited_sources)):
                raise ModelRetry("source citations must carry the trusted identity of every reviewed run; "
                                 "mixed or missing source identities cannot share a review")
            required_plan_items = {"test-plan", "reported-condition"}
            if not required_plan_items <= {item.item_id for item in review_items if item.kind == "plan"}:
                raise ModelRetry("each validity review must cite the full test-plan and reported-condition items")
            if all((review.source_linked, review.condition_exercised,
                    review.assertions_relevant, review.dependency_scope_valid)):
                required_reads = [item for item in inputs.items if item.kind == "patch"
                                  or item.item_id in required_plan_items or item in cited_sources]
                for item in required_reads:
                    if any(not any(read.item_id == item.item_id and read.start_line <= line <= read.end_line
                                   for read in reads)
                           for line in range(1, len(item.content.splitlines()) + 1)):
                        raise ModelRetry("affirmative test validity requires complete reads of every patch, "
                                         "the test-plan, reported-condition and cited source items")
            quoted_review = review.model_dump() | {"rationale": quoted(review.rationale)}
            reviews.append(quoted_review)
            review_sha256 = sha256(json.dumps(quoted_review, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            updated = []
            for run in runs:
                # Source identities and plan/patch binding come from trusted inputs, never draft identifiers.
                validity = (TestValidity(artifact_sha256=review_sha256,
                    observation_plan_sha256=inputs.plan.review_digest, source_sha256=run.source_sha256,
                    source_linked=review.source_linked, condition_exercised=review.condition_exercised,
                    assertions_relevant=review.assertions_relevant,
                    dependency_scope_valid=review.dependency_scope_valid) if run.source_sha256 else None)
                updated.append(run.model_copy(update={"test_validity": validity}))
            evidence = evidence.model_copy(update={review.revision: tuple(updated)})
    result = assess(evidence)
    return EvidenceAssessment.model_validate(draft.model_dump() | {
        "application_observations": [quoted(o) for o in draft.application_observations],
        "sandbox_observations": [quoted(o) for o in draft.sandbox_observations],
        "interpretation": quoted(draft.interpretation),
        "validity_reviews": reviews if inputs.plan.observation_mode == "unit_test" else [],
        "admission": admit(proposal, result), "gate_limitations": result.limitations,
        "gate_result": result, "evidence": evidence,
    })
