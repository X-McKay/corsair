---
id: PLAN-0093
kind: plan
title: Unit tests at application seams
status: complete
updated: 2026-10-13
related: [SPEC-0078]
---

# Unit tests at application seams

## Objective and dependencies

Implement [SPEC-0078](../specs/SPEC-0078-unit-test-observation.md) on base 1815f75498c0acbbd35dcaa20a42cef737e76866. Preserve unrelated open-PR review records. Initial implementation did not authorize publication; subsequent user instructions authorized PR publication, review corrections and proportionate evaluation. No merge or deployment is authorized. User explicitly authorized parallel Sol 6.1 agents and adjusting existing roles/tools as needed.

## Steps

- [x] Introduce planner unit-observation contracts and native authoring policy.
- [x] Update authoritative documentation and shared development skills.
- [x] Bind independent assessment validity review to exact source and frozen tests; connect shared disposition/composition.
- [x] Exercise native controlled-dependency example, refusal cases and affected consumers.
- [x] Compare frozen isolated agent evaluations, review and record handoff.

## Validation and progress

Planning frozen scripted evaluation: 12/12 clean before and after, zero failures; focused tests 82 passed. Authoring focused tests 100 passed; scripted after evaluation 20 cases with no failures. Initial restricted-socket planner/authoring checks stalled and were interrupted (exit 130); escalated host retries passed. These use host fixtures, not sandbox or live model qualification. Assessment baseline completed under /tmp/corsair-unit-assessment-before. Final counts and limits will be recorded after integration.

## Decisions and next action

Use the existing assessment agent for independent semantic review, rather than require a human-supplied validity record or introduce a sixth agent. Native execution remains separate. Source visibility and valid assertion classification are required; optional instrumentation cannot substitute for an unrelated unit assertion. Continue integration and checks before finalizing.

Final implementation and qualification limits: [HANDOFF-0123](../handoffs/HANDOFF-0123-unit-test-observation.md). Full offline second run 2016 passed, 1 event-order assertion failed, 1 skipped; final affected checks after the event-order correction 63 passed. Frozen scripted planning/authoring/assessment comparisons remain 12/12, 20/20 and 54/54 respectively. Earlier failures, source-binding review fixes and unrun live checks are retained in the handoff. Completion means the offline implementation scope is delivered, not live model/runtime qualification.

PR publication validation (2026-10-13): integrated main 2a3dcb2, preserving candidate-free runs and the extracted preparation port. Full offline suite now passes: **2064 passed, 6 skipped, 12 inherited warnings in 56.42 s**, log `/tmp/corsair-unit-pr-tests.log`. This includes a new no-candidate unit-review composition case. Added ongoing-development guidance to the development guide, PR checklist and handoff skill. See [HANDOFF-0121](../handoffs/HANDOFF-0121-unit-test-pr.md).

PR #130 review follow-up (2026-10-13): identified and fixed incomplete evidence being eligible for full-patch semantic affirmation, isolated authoring evaluation applying legacy witness restrictions to unit doubles, and shared failure-name mapping assuming pytest separators. Affirmative review now requires complete evidence and tool-read coverage of every patch, full plan/reported condition and cited source. Native identity syntax stays in the runner port. Removed unused injected-validity composition path and exception-driven normal unit routing. Simplified common skills and allowed source reads needed to understand relevant helpers/dependencies. Validation and publication are recorded in HANDOFF-0122.

Final PR review validation: full offline suite **2086 passed, 6 skipped, 12 inherited warnings in 56.16 s**, `/tmp/corsair-pr130-review-full.log`. The user then emphasized actual control and exploit probe execution: made both roles explicit in design/skills and added missing/skipped-either-probe regressions. Final gate/workflow subset30passed. After that guidance, frozen scripted planning12/12, authoring20/20 and assessment54/54 remain clean with no evaluator failures (`/tmp/corsair-pr130-{planning,authoring,assessment}-probes`). No live semantic qualification claimed.

## PR feedback corrections (complete offline)

Separate outcome-blind test-validity review from execution/result assessment using the existing agent and tools. Preserve exactly two executed probes per revision, immutable review binding, generic observation contracts and optional instrumentation. Fix candidate source capture and evidence access ceilings within the supported acquisition envelope; restore measured framework facts as harness data; add new unit-mode evaluation sets without rewriting legacy baselines. Correct explicit target-not-reached rejection. Matching observation kinds and revision differentials are supporting context, not sufficient calibration or source-linkage proof. Renumber SPEC-0078, PLAN-0093 and historical HANDOFF-0123 to resolve reported reservations.


Final feedback validation: **2108 passed, 6 skipped, 12 inherited warnings** in the full offline suite; added durable review-payload converter check1passed. Legacy scripted planning12/12, authoring20/20 and assessment54/54 remain clean. New frozen unit sets: planning2cases/4attempts, authoring2cases/4attempts, assessment7cases/7attempts, all clean. Earlier failed ordering/record/test-harness attempts are retained in [HANDOFF-0124](../handoffs/HANDOFF-0124-unit-review-feedback.md). Evidence retained under ignored `.runs/pr130-review-feedback/` and `.runs/evals/`. Live evaluation was rejected by automatic approval review pending explicit authorization for the configured external destination; no live semantic-quality improvement is claimed. Implementation corrections are complete; live qualification remains a separate blocked gate.


Agent skill/tool audit: [HANDOFF-0125](../handoffs/HANDOFF-0125-unit-skill-audit.md) corrects phase-specific evidence/citation guidance and explicitly uses typed harness assertion facts in planning/authoring. No additional tools or agents needed. Affected tests253passed; frozen legacy12/20/54 and unit2/2/7 scripted cases all clean. Skill metadata and diff checks pass. Live semantic qualification remains outstanding.
