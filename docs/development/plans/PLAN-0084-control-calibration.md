---
id: PLAN-0084
kind: plan
title: Control calibration of planned absences (SPEC-0040)
status: complete
updated: 2026-10-13
related: [SPEC-0040, PLAN-0044, SPEC-0033, SPEC-0027, HANDOFF-0107]
---

# Control calibration of planned absences (SPEC-0040)

## Objective and dependencies

Al asked (2026-10-13 18:16Z) that the chain reliably reach LIKELY_NOT_EXPLOITABLE. The [SPEC-0040](../specs/SPEC-0040-typed-planned-witness.md) absence mapping (`no_file_open`) was held to the candidate revision until the control calibration landed, so a reported revision that is safe because it never opens the sentinel stayed `inconclusive`. This plan builds the calibration only: the witness request still comes from the operator envelope here (SPEC-0073 on PR #109 builds it from the framework table's recorders), and the SPEC-0027 gates, stage order, witness requirement and matrix rows are unchanged.

## Steps

- [x] `nodes/witness.py`: `Calibration(test_id, subject)`; for a `no_file_open` plan an attributed absence counts only when the same run's control call phase is complete, paired, untruncated, entered the target and recorded an on-stack open whose normalized path ends in the control subject. Otherwise the witness is refused (`absence not calibrated: <reason>`). An observed effect and an exception-type safe behavior are unchanged. No probe change: the probe already records every on-stack open per test.
- [x] `composition/direct.py`: the absence mapping applies to both revisions, with the plan's control as the calibration.
- [x] Fixture: `fixture_case("not-exploitable")` and `reviewed_runners(..., case)` run the confined source at every revision, so the composition tests cover a report that does not hold.
- [x] Tests: unit refusals per calibration condition, a real-probe calibration, composition tests for a calibrated baseline absence (`not_reproduced`), an uncalibrated one (`inconclusive`) and the exception route.
- [x] SPEC-0040 status, CURRENT.md, HANDOFF-0107.

## Validation and progress

See [HANDOFF-0107](../handoffs/HANDOFF-0107-control-calibration.md) for the commands and results. Not live-qualified: no model ran; the run thread's live not-exploitable fixture runs use the exception route on the earlier run-kit branch.

## Decisions and next action

- Calibration guards absences only. SPEC-0040 says the run's witness is refused when the control is not observed; applied to every witness that would also refuse an observed effect, which is its own evidence that the probe records it, and would turn reproduced runs inconclusive for a control subject the author spelled differently. Recorded in SPEC-0040.
- The calibration shows the probe records the target's file opens in this run; it does not show the security payload aimed at the sentinel. A payload that misses (resolves to another file name) can still read as an absence. Left open in SPEC-0040.
- Next: the live planner and author must choose `no_file_open` with a control that opens its subject; measure on the not-exploitable fixture once this merges with #113.
