---
id: PLAN-0090
kind: plan
title: Unit tests at application seams
status: complete
updated: 2026-10-13
related: [SPEC-0075]
---

# Unit tests at application seams

## Objective and dependencies

Implement [SPEC-0075](../specs/SPEC-0075-unit-test-observation.md) on base 1815f75498c0acbbd35dcaa20a42cef737e76866. Preserve unrelated open-PR review records. No merge, publication, provider calls or deployment authorized by this implementation. User explicitly authorized parallel Sol 6.1 agents and adjusting existing roles/tools as needed.

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

Final implementation and qualification limits: [HANDOFF-0120](../handoffs/HANDOFF-0120-unit-test-observation.md). Full offline second run 2016 passed, 1 event-order assertion failed, 1 skipped; final affected checks after the event-order correction 63 passed. Frozen scripted planning/authoring/assessment comparisons remain 12/12, 20/20 and 54/54 respectively. Earlier failures, source-binding review fixes and unrun live checks are retained in the handoff. Completion means the offline implementation scope is delivered, not live model/runtime qualification.

PR publication validation (2026-10-13): integrated main 2a3dcb2, preserving candidate-free runs and the extracted preparation port. Full offline suite now passes: **2064 passed, 6 skipped, 12 inherited warnings in 56.42 s**, log `/tmp/corsair-unit-pr-tests.log`. This includes a new no-candidate unit-review composition case. Added ongoing-development guidance to the development guide, PR checklist and handoff skill. See [HANDOFF-0121](../handoffs/HANDOFF-0121-unit-test-pr.md).
