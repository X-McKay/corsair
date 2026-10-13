---
id: SPEC-0040
kind: spec
title: Typed planned witness for the test planner
status: accepted
updated: 2026-10-13
related: [SPEC-0022, SPEC-0027, SPEC-0033, PLAN-0038, PLAN-0044, SPEC-0023]
---

# Typed planned witness for the test planner

## Goal and scope

PLAN-0038 removed the planner's mechanical failures, but its held-out plans still state witnesses in prose that the facility contradicts (an event the call raises anyway, an event the facility never produces, a link path instead of its target), choose payloads whose effect no listed facility records, and carry identifiers from unrelated cases. Three prompt iterations moved these only partly. This spec replaces the free-form security witness with a typed planned witness that deterministic code can check when the plan is admitted and that the SPEC-0033 probe can bind at execution, so a wrong witness is refused or shown wrong by evidence instead of by review.

In scope: the planner contract, the operator's environment evidence, plan admission checks, the evaluator, and the mapping from a plan to the SPEC-0033 `WitnessRequest` in place of the per-case operator envelope. Excluded: new probe effect kinds beyond those the probe already records, other languages, durable mode changes and any change to the SPEC-0027 gates. Implemented in stages under PLAN-0044: the contract, admission checks, prompt and evaluator first; the composition binding and control calibration below follow once the planner is measured.

## Boundaries and design

**Operator-owned facility kinds.** `EnvironmentEvidence` gains `witness_facilities: tuple[WitnessFacility, ...]` (default empty), each `{id: Identifier, kind: Literal["file_open", "process_start", "socket_connect"], description: Fact}`, with unique ids. The kinds are the in-process audit events the planner can name; the SPEC-0033 probe records only `file_open` today, so a plan naming another kind is admitted but its witness stays unbound at execution (refused, the gates stay `inconclusive`) until the probe records that kind. The existing prose `observation_facilities` stay for context. The facility list is operator data, never model-editable.

**Planned witness.** Each `TestSpecification` gains `witness: PlannedWitness{facility: Identifier, effect: Literal[...], subject: ScratchPath, expectation: Literal["occurs", "absent"]}`. For `file_open`, `subject` is a path relative to the scratch location (no absolute path, no `..`, no `~`), naming the sentinel the effect would touch, written canonically (no `./`, repeated or trailing separators, or `.` components) so distinct subjects are distinct files; for the other kinds it is a token (`[A-Za-z0-9_.:/-]+`) that appears in the recorded arguments or address. The prose `observable_witness` remains as explanation only and is never read by a gate.

**Admission checks** (in the planner's output function, as `ModelRetry`, and repeated by the evaluator):
- `facility` names a listed facility and `effect` equals its kind; an unknown facility means no listed facility observes the effect, so the plan must be unsupported.
- The control expects `occurs` on a benign subject and the security test expects `absent` on the adversarial subject, and the two subjects differ.
- The security subject (its file name for `file_open`) appears in the security fixture setup or input, so the payload aims at the sentinel. The evaluator's `scratch` heuristic over fixture prose is unchanged.
- `security_expectation.safe_behavior` is either an exception type that `required_behavior` names, or the identifier `no_<effect>`; any other identifier is refused.

**Interim binding.** Until the composition builds the request from the plan, it requests the operator envelope only when the plan's security witness is a `file_open` whose subject is exactly the envelope's effect file (a directory-prefixed subject names another path); any other planned effect or subject runs without a witness, so its gates stay `inconclusive` instead of borrowing the envelope's file-open evidence.

**Absence as the safe behavior.** When the plan's `safe_behavior` is `no_file_open`, the SPEC-0033 mapping records that identity for an attributed, paired security call phase without the planned open, however the target exited, so a fix that rejects or returns normally without the effect matches the plan at the gate. The probe also counts opens of the planned file off the target's stack during the call phase, on another thread or on the test thread after the target was first entered (an event-loop callback the target scheduled); any such open makes the effect `unknown`, so moving the open off the target's stack is never an absence. Only the test body's reads before its first call are not counted; a test that reads the sentinel after the call therefore gets `unknown`, which fails closed (child processes are not observed). The mapping applies on both revisions only when the control calibration below holds in the same run; an uncalibrated absence refuses the witness, so it stays `inconclusive` instead of becoming `not_reproduced`. `verified` still needs a baseline that reproduced the effect.

**Calibration by the control at execution.** The plan's subjects replace the operator envelope: the composition builds `WitnessRequest(target_path, target_symbol, effect_name=subject)` from the admitted plan, still bound to the admitted identification target. At execution the control witness must be observed as planned on both revisions; if it is not, the planned witness is wrong for this facility and the run's witness is refused with that reason, so the gates stay at `inconclusive` rather than trusting an absence. This turns "a witness the facility never records" into evidence instead of a review finding. Implemented for absences (PLAN-0084): a `no_file_open` safe behavior counts only when the control's call phase recorded an on-stack open whose path ends in the control subject; an observed effect and an exception-type safe behavior need no calibration, since they are their own evidence that the probe records the call. Calibration shows the facility records the target's opens, not that the security payload aimed at the sentinel: a payload that resolves to another file name still reads as absent.

**Payload choice.** The skill asks for an adversarial input whose effect lands on the security subject inside the scratch location (for example a payload that opens or creates the sentinel) instead of the issue's own payload when that would run a real command. Harmlessness is a prompt rule; the sandbox and the scratch-relative subject bound the consequence.

## Acceptance and validation

Offline: contract tests for each refusal above; the development reference plans (and the authoring and fixture E2E plans built from them) carry typed witnesses and are still admitted; the two earlier held-out sets are retired, because their frozen environments list no typed facility; the composition builds the witness request from the plan and refuses a run whose control witness is absent. Evaluator: a `planned_witness` check comparing facility, effect and expectation with the oracle, replacing the substring `witness` markers for typed cases. Live: development set first; then a third held-out set written and reviewed by agents other than the prompt author and frozen by manifest before one run, under PLAN-0038's pre-registered criteria.

## Decisions and open questions

Accepted by Al (decision card, 2026-10-13). Implemented under PLAN-0044 (PR #44): contract, admission (including canonical subjects and the interim envelope refusal), prompt v7 and evaluator; control calibration of absences implemented under PLAN-0084 (HANDOFF-0107); the plan-built witness request is SPEC-0073's (PR #109). Planner v7 not qualified on the third held-out set (PLAN-0044).

Open: whether `subject` should also allow an argument token for future process or network effects; whether the control calibration should run in discovery before the frozen runs; whether a missing facility should be an admission refusal or a typed `unsupported` with the facility gap filled in automatically.
