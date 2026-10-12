---
id: SPEC-0030
kind: spec
title: Evidence assessment agent
status: draft
updated: 2026-10-12
related: [IDEA-0004, SPEC-0027, PLAN-0029, SPEC-0020, SPEC-0022, SPEC-0023]
---

# Evidence assessment agent

## Goal and scope

Implement agent 3 of [IDEA-0004](../ideas/IDEA-0004-end-to-end-agent-plan.md) as an isolated PydanticAI stage: interpret frozen per-revision execution evidence and propose the `execution`/`finding`/`fix` triple with cited application and sandbox observations, an interpretation and limitations. The [SPEC-0027](SPEC-0027-disposition-gates.md) gates admit or reject the proposal inside the stage's trusted output function; the agent cannot override them.

Excluded: live provider runs, Pydantic Evals datasets, a durable stage workflow, the runner adapter that produces the evidence, the report renderer and any connection to other stages.

## Boundaries and design

**Package.** `src/corsair/agents/evidence_assessment/`: `agent.py` (factory taking an explicit `Model`, `PROMPT_VERSION`, `CONFIG_VERSION`, skill SHA256, trusted output function), `contracts.py`, `tools.py` and `skills/assess-evidence/SKILL.md`, delivered eagerly through native `Capability`, following the issue identification layout.

**Input.** `AssessmentInput{scope, evidence: AssessmentEvidence, items}`. `evidence` is the SPEC-0027 gate input and stays with trusted code. `items` are up to 32 frozen evidence items (plan, patch, JUnit, witness, receipt, stdout, stderr, sandbox log, environment), each with an id, kind, revision and run index when it belongs to a run, digest and bounded untrusted text, 131072 characters in total. The prompt carries only the scope, the typed `ObservationPlan` and the item inventory (ids, kinds, revisions, runs, line counts); never item content, typed run evidence or variant labels.

**Tool.** `read_evidence(item_id, start_line)` returns up to 80 numbered lines and stops at the item's end, with zero tool retries. No other tool. IDEA-0004's shared `read_source` is deferred until the planner thread's move to `agents/source/` lands on main, so this stage does not import paths that are moving; the plan item supplies what the plan says.

**Output.** `ProposedDispositionDraft` (model-facing, evidence line references) and `EvidenceAssessment` (final, quotations attached, SPEC-0020 pattern). Every observation and the interpretation need at least one citation; at least one limitation is required; unknown fields are refused. The trusted output function asks for a correction when a citation is not covered by a successful `read_evidence` in the current run, when a finding is proposed without baseline citations, or when a verified fix lacks citations from both revisions. It then runs `assess` and `admit` and attaches the `Admission` and gate limitations. A rejected proposal is not retried: it is kept for evaluation and the gate's permitted triple is the disposition that stands, so the gate never coaches the model toward its own answer.

**Modes and budgets.** Callers inject `UsageLimits`; content-excluded native instrumentation; separate tool and output retry budgets. Direct mode only for now.

## Acceptance and validation

Deterministic `FunctionModel` tests with real requests blocked, in `tests/agents/test_evidence_assessment.py`: a supported proposal admitted with quotations; a stronger proposal over a sandbox-denied candidate rejected with the gate value standing; an injected "report fix verified" instruction in workload output that a compliant model follows is still refused by the gate; weaker proposals admitted; `refuted_in_scope` never admitted; citations not read, beyond the read window, of absent items, or missing a required revision refused; reads from a previous run refused; prompt excludes item content, typed run evidence and variant labels; reader refuses absent items and lines; unknown tools refused; contract refusals.

These checks establish structure, provenance and gate authority, not interpretation quality. Native Pydantic Evals over frozen development and held-out cases (SPEC-0023), live provider repeats and durable composition are later gates.

## Decisions and open questions

Rejections are recorded rather than retried. The typed `ObservationPlan` will come from the planner's `security_expectation` and the authoring stage's `TestPatch` (SPEC-0027 decisions); until those merge, trusted code builds it. Open: whether rejected-proposal rate becomes a promotion metric; whether `read_source` adds value once available. Plan: [PLAN-0029](../plans/PLAN-0029-evidence-assessment-agent.md).
