"""Bind independent test review and cited observations to frozen inputs; deterministic gates decide."""

from hashlib import sha256
import json

from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ModelRequest, ToolReturnPart

from corsair.core.disposition import Disposition, TestValidity, Admission, admit, assess

from .contracts import AssessmentInput, EvidenceAssessment, EvidenceRead, ProposedDispositionDraft, ValidityInput
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


def _references(review):
    for probe in (review.control, review.exploit):
        yield probe.production_binding.call_site
        if probe.production_binding.definition_site is not None:
            yield probe.production_binding.definition_site
        for observation in probe.observations:
            yield from observation.citations


async def finalize_assessment(ctx: RunContext[AssessmentDependencies],
                              draft: ProposedDispositionDraft) -> EvidenceAssessment:
    inputs = ctx.deps.inputs
    reads = [EvidenceRead.model_validate(part.content)
             for message in ctx.messages if isinstance(message, ModelRequest) and message.run_id == ctx.run_id
             for part in message.parts if isinstance(part, ToolReturnPart)
             and part.tool_name == READ_EVIDENCE_TOOL and part.outcome == "success"]
    observations = (*draft.application_observations, *draft.sandbox_observations, draft.interpretation)
    references = [reference for observation in observations for reference in observation.citations]
    references += [reference for review in draft.validity_reviews for reference in _references(review)]
    items = {item.item_id: item for item in inputs.items}
    problems = []
    for reference in references:
        if not any(read.item_id == reference.item_id and read.start_line <= reference.start_line
                   and reference.end_line <= read.end_line for read in reads):
            problems.append(f"read_evidence must cover citation {reference.item_id}:{reference.start_line}-{reference.end_line}")
    cited = {reference.item_id for reference in references}
    if not isinstance(inputs, ValidityInput):
        if draft.validity_reviews:
            problems.append("disposition assessment cannot author or change frozen test validity")
        if inputs.plan.observation_mode == "effect_witness" and draft.finding in ("reproduced", "not_reproduced"):
            problems.append(_witness_problem(inputs, cited, "baseline", f"finding {draft.finding}", "finding inconclusive"))
        if inputs.plan.observation_mode == "effect_witness" and draft.fix == "verified":
            problems += [_witness_problem(inputs, cited, revision, "fix verified", "fix not_verified")
                         for revision in ("baseline", "candidate")]
    else:
        if (draft.execution, draft.finding, draft.fix) != ("unknown", "inconclusive", "not_applicable") or draft.application_observations or draft.sandbox_observations:
            problems.append("pre-execution review requires unknown/inconclusive/not_applicable and no execution observations")
        if len({review.revision for review in draft.validity_reviews}) != len(draft.validity_reviews):
            problems.append("provide at most one validity review per revision")

        def required(observation, *, kinds=(), ids=(), label):
            found = [items[c.item_id] for c in observation.citations if c.item_id in items]
            missing_kinds = set(kinds) - {item.kind for item in found}
            missing_ids = set(ids) - {item.item_id for item in found}
            if missing_kinds or missing_ids:
                problems.append(f"{label} evidence must cite " + ", ".join(
                    [f"kind {kind}" for kind in sorted(missing_kinds)] + sorted(missing_ids)))

        for review in draft.validity_reviews:
            source_identity = inputs.revision_sources.get(review.revision)
            if source_identity is None:
                problems.append(f"{review.revision} review names an absent revision")
            for role, probe, test_id in (("control", review.control, inputs.plan.control_test_id),
                                        ("exploit", review.exploit, inputs.plan.security_test_id)):
                label = f"{review.revision} {role}"
                if probe.test_id != test_id:
                    problems.append(f"{label} test_id must be {test_id}")
                binding = probe.production_binding
                call_item = items.get(binding.call_site.item_id)
                definition = items.get(binding.definition_site.item_id) if binding.definition_site else None
                if call_item is None or call_item.kind != "patch":
                    problems.append(f"{label} call_site must name the frozen patch invocation")
                if binding.status == "production":
                    if definition is None or definition.kind != "source":
                        problems.append(f"{label} production definition_site must name captured source, never a test-local copy")
                    required(binding.evidence, kinds=("patch", "source"), label=f"{label} production binding")
                elif binding.status == "copied" and (definition is None or definition.kind != "patch"):
                    problems.append(f"{label} copied definition_site must name the actual copy in the frozen patch")
                elif binding.status == "unknown" and binding.definition_site is not None:
                    problems.append(f"{label} unresolved binding must use definition_site null")
                required(probe.input_exercise.evidence, kinds=("patch",),
                         ids=("test-plan", "reported-condition"), label=f"{label} input/preconditions")
                required(probe.assertion.evidence, kinds=("patch",),
                         ids=("test-plan", "reported-condition"), label=f"{label} assertion property")
                required(probe.dependencies.evidence, kinds=("patch",), label=f"{label} dependency substitutions")
                dependencies = probe.dependencies
                if dependencies.scope == "none" and dependencies.substitutions:
                    problems.append(f"{label} dependency scope none requires no substitutions")
                if dependencies.scope in ("dependencies_only", "entry_point_replaced", "security_logic_replaced") and not dependencies.substitutions:
                    problems.append(f"{label} list the actual substituted symbols and behavior")
            for reference in _references(review):
                item = items.get(reference.item_id)
                if item is not None and item.kind == "source" and (item.revision != review.revision or item.source_sha256 != source_identity):
                    problems.append(f"{review.revision} source citations must carry its trusted source identity")
            affirmative = all((review.source_linked, review.condition_exercised,
                               review.assertions_relevant, review.dependency_scope_valid))
            if affirmative:
                relevant = [item for item in inputs.items if item.kind in ("plan", "patch")
                            or (item.kind == "source" and item.revision == review.revision)]
                if any(not item.complete for item in relevant):
                    problems.append(f"{review.revision} incomplete source, patch or plan cannot support affirmative validity")
                for item in inputs.items:
                    if item.kind == "patch" or item.item_id in ("test-plan", "reported-condition"):
                        if any(not any(read.item_id == item.item_id and read.start_line <= line <= read.end_line for read in reads)
                               for line in range(1, len(item.content.splitlines()) + 1)):
                            problems.append(f"{review.revision} affirmative validity requires complete read_evidence windows for {item.item_id}")
    if problems := list(dict.fromkeys(problem for problem in problems if problem)):
        raise ModelRetry("; ".join(problems))

    def excerpt(reference):
        return ctx.deps.read_evidence(reference.item_id, reference.start_line, reference.end_line).model_dump()

    def quoted(observation):
        return {"statement": observation.statement, "citations": [excerpt(c) for c in observation.citations]}

    proposal = Disposition(execution=draft.execution, finding=draft.finding, fix=draft.fix)
    if isinstance(inputs, ValidityInput):
        reviews, bound = [], {}
        for review in draft.validity_reviews:
            retained = review.model_dump()
            for role in ("control", "exploit"):
                probe = getattr(review, role)
                for check in ("production_binding", "input_exercise", "assertion", "dependencies"):
                    retained[role][check]["evidence"] = quoted(getattr(probe, check).evidence)
                retained[role]["production_binding"]["call_site"] = excerpt(probe.production_binding.call_site)
                definition = probe.production_binding.definition_site
                retained[role]["production_binding"]["definition_site"] = excerpt(definition) if definition else None
            reviews.append(retained)
            digest = sha256(json.dumps(retained, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            bound[review.revision] = TestValidity(artifact_sha256=digest,
                observation_plan_sha256=inputs.plan.review_digest,
                source_sha256=inputs.revision_sources[review.revision],
                source_linked=review.source_linked, condition_exercised=review.condition_exercised,
                assertions_relevant=review.assertions_relevant, dependency_scope_valid=review.dependency_scope_valid)
        return EvidenceAssessment.model_validate(draft.model_dump() | {
            "application_observations": [], "sandbox_observations": [],
            "interpretation": quoted(draft.interpretation), "validity_reviews": reviews,
            "bound_validity": bound, "admission": Admission(admitted=True, disposition=proposal, rejections=()),
            "gate_limitations": (),
        })
    result = assess(inputs.evidence)
    return EvidenceAssessment.model_validate(draft.model_dump() | {
        "application_observations": [quoted(o) for o in draft.application_observations],
        "sandbox_observations": [quoted(o) for o in draft.sandbox_observations],
        "interpretation": quoted(draft.interpretation), "validity_reviews": [],
        "admission": admit(proposal, result), "gate_limitations": result.limitations,
        "gate_result": result, "evidence": inputs.evidence,
    })
