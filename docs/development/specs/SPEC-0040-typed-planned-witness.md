---
id: SPEC-0040
kind: spec
title: Typed planned witness for the test planner
status: draft
updated: 2026-10-13
related: [SPEC-0022, SPEC-0027, SPEC-0033, PLAN-0038, SPEC-0023]
---

# Typed planned witness for the test planner

## Goal and scope

PLAN-0038 removed the planner's mechanical failures, but its held-out plans still state witnesses in prose that the facility contradicts (an event the call raises anyway, an event the facility never produces, a link path instead of its target), choose payloads whose effect no listed facility records, and carry identifiers from unrelated cases. Three prompt iterations moved these only partly. This spec replaces the free-form security witness with a typed planned witness that deterministic code can check when the plan is admitted and that the SPEC-0033 probe can bind at execution, so a wrong witness is refused or shown wrong by evidence instead of by review.

In scope: the planner contract, the operator's environment evidence, plan admission checks, the evaluator, and the mapping from a plan to the SPEC-0033 `WitnessRequest` in place of the per-case operator envelope. Excluded: new probe effect kinds beyond those the probe already records, other languages, durable mode changes and any change to the SPEC-0027 gates. Design only: nothing here is implemented yet.

## Boundaries and design

**Operator-owned facility kinds.** `EnvironmentEvidence` gains `witness_facilities: tuple[WitnessFacility, ...]`, each `{id: Identifier, kind: Literal["file_open", ...], description: Fact}`. A kind is added only when the execution probe can record it; today that is `file_open` (SPEC-0033). The existing prose `observation_facilities` stay for context. The facility list is operator data, never model-editable.

**Planned witness.** Each `TestSpecification` gains `witness: PlannedWitness{facility: Identifier, effect: Literal[...], subject: ScratchPath, expectation: Literal["occurs", "absent"]}`. `subject` is a path relative to the scratch location (no absolute path, no `..` after normalization), naming the sentinel the effect would touch. The prose `observable_witness` remains as explanation only and is never read by a gate.

**Admission checks** (in the planner's output function, as `ModelRetry`, and repeated by the evaluator):
- `facility` names a listed facility and `effect` equals its kind; an unknown facility means no listed facility observes the effect, so the plan must be unsupported.
- The control expects `occurs` on a benign subject and the security test expects `absent` on the adversarial subject, and the two subjects differ.
- The security subject appears in the security fixture setup or input (the payload must aim at the sentinel), and nothing in fixture setup reaches outside the scratch location (the existing scratch check, now on a typed path).
- `security_expectation.safe_behavior` is either an exception type that `required_behavior` names, or the identifier `no_<effect>`; any other identifier is refused.

**Calibration by the control at execution.** The plan's subjects replace the operator envelope: the composition builds `WitnessRequest(target_path, target_symbol, effect_name=subject)` from the admitted plan, still bound to the admitted identification target. At execution the control witness must be observed as planned on both revisions; if it is not, the planned witness is wrong for this facility and the run's witness is refused with that reason, so the gates stay at `inconclusive` rather than trusting an absence. This turns "a witness the facility never records" into evidence instead of a review finding.

**Payload choice.** The skill asks for an adversarial input whose effect lands on the security subject inside the scratch location (for example a payload that opens or creates the sentinel) instead of the issue's own payload when that would run a real command. Harmlessness is a prompt rule; the sandbox and the scratch-relative subject bound the consequence.

## Acceptance and validation

Offline: contract tests for each refusal above; the reference plans of the development and both held-out sets rewritten with typed witnesses and still admitted; the composition builds the witness request from the plan and refuses a run whose control witness is absent. Evaluator: a `planned_witness` check comparing facility, effect and expectation with the oracle, replacing the substring `witness` markers for typed cases. Live: development set first; then a third held-out set written and reviewed by agents other than the prompt author and frozen by manifest before one run, under PLAN-0038's pre-registered criteria.

## Decisions and open questions

Open: whether `subject` should also allow an argument token for future process or network effects; whether the control calibration should run in discovery before the frozen runs; whether a missing facility should be an admission refusal or a typed `unsupported` with the facility gap filled in automatically.
