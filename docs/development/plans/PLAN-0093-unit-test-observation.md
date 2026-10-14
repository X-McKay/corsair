---
id: PLAN-0093
kind: plan
title: Unit tests at application seams
status: in_progress
updated: 2026-10-13
related: [SPEC-0078, ISSUE-0009]
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


Merge/live follow-up: user approved proceeding; PR #130 merged at df5c661 after green CI. Optional-witness rule accepted without a mandatory recorder follow-up. Six-suite live evaluation command was rejected before execution by automatic approval review pending explicit authorization for repository-derived prompts and fixture/source data to the configured external endpoint. No live runs or baseline promotion occurred. [HANDOFF-0126](../handoffs/HANDOFF-0126-merged-live-eval-admission.md) records exact source, discovered baselines and comparability limits. Offline implementation remains complete; live qualification is blocked on admission.


Live admission resumed: user explicitly authorized llm.almckay.io/v1 as their self-hosted model. Six suites launched sequentially on RIG0 against exact merged source df5c661; no provider/budget changes or baseline promotion. Evidence root `.runs/pr130-live-merged/`. Results pending; earlier admission rejection retained as history.


Initial live unit results (exact merge df5c661, current configured Qwen provider): planning0/4clean (3 native-ID contract failures; remaining accepted plan failed an exact adversarial marker despite a valid equivalent SQL tautology), authoring4/4clean under injected/static runner observations (generated tests not executed), assessment2/7clean. Assessment semantically approved copied and wrong-module targets in drafts blocked only by citation errors; a benign-input exploit case received all-true bound validity and passed the output contract, failing its semantic oracle. Campaign semantic qualification is blocked. Legacy suites continue unchanged; no baseline promotion or prompt correction during measurement.

## Accepted follow-up: probe-level validity evidence

User approved the live-evaluation design improvements. Work from merged df5c661 on codex/probe-validity-evidence. Preserve six-suite before measurements in the unchanged /tmp/corsair-pr130-live checkout and ignored .runs/pr130-live-merged. Implementation lanes: assessment contract/validation/skill and consumers; planning identity formatting at the runner port; versioned evaluator robustness and failure classification. Shared documentation and development/review skills carry the rule forward.

- [x] Replace broad model validity flags with cited per-probe production binding, condition, assertion and dependency checks; derive revision flags and retain immutable binding.
- [x] Simplify model-facing native identity fields and aggregate actionable review contract errors without weakening gates.
- [x] Version evaluator corrections, preserve legacy scores, distinguish semantic false approvals from contract/evaluator failures.
- [ ] Run affected offline/scripted checks, independent review and comparable live suites; retain unsuccessful attempts and no automatic baseline promotion.
- [ ] Record results, qualification limits and handoff; publish follow-up under standing PR authorization.

Baseline planning development completed 4/12 clean: five task/contract failures and three returned unit plans rejected by legacy witness expectations. This mixes contract failures with obsolete evaluator assumptions; do not describe it as a pure semantic regression. Unit results and admitted assessment false approval remain as recorded above. Campaign qualification stays blocked pending corrected live evidence.

The live semantic blocker and its resolution criteria are tracked in [ISSUE-0009](../issues/ISSUE-0009-unit-review-semantic-validity.md). The user’s self-hosted endpoint authorization persists; no cost or usage approval is needed for proportionate live evaluation.

Follow-up implementation review removed the remaining model-facing raw native-ID alternative: runner formatting is the only new draft path, while frozen scripted outputs are adapted outside production contracts. Assessment stays in the existing agent with four concrete checks per probe; no additional agent, universal parser, recorder or repair loop. Tool/skill audit clarified evidence inventory IDs, pagination boundaries and actionable read errors without expanding budgets or authority. Read-only historical reviews remain parseable; full quoted reviews are retained and oversized final-assessor views use explicit summaries without quotation bodies.

Validation attempt retained: an overly broad bare pytest invocation included live-qualification tests, which refused missing explicit admission arguments; it was interrupted (1331passed,30skipped,33setup errors,1unrelated terminal-environment failure). The terminal fixture saw TERM=dumb/NO_COLOR=1. Use the Makefile offline selection with a normal terminal environment for final checks; no live runtime qualification is claimed. Initial process guard4passed1failed because it treated development manifests as held-out; corrected only the secrecy condition, preserving all manifest hash checks and historical records.

Final offline implementation: 2,163 passed, 6 skipped, 12 warnings in 63.42 s using the Makefile offline selection with 4 workers, TERM=xterm-256color and NO_COLOR unset (`/tmp/corsair-probe-validity-offline-final.log`). The prior correct-selection run had 2,162 passed and 1 old-protocol replay failure; its fixture boundary was adapted without modifying the recorded response, then 18 focused checks passed and the full run passed. Independent review and skill/tool audit completed. Before authoring development is 3/20 clean with 5 task failures; it uses injected runner observations, not generated-test execution. Original assessment development remains running.
