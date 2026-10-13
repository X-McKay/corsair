---
id: PLAN-0056
kind: plan
title: Early stops and actionable setup blockers
status: complete
updated: 2026-10-13
related: [SPEC-0052]
---

# Early stops and actionable setup blockers

## Objective and dependencies

Implement SPEC-0052 on current main 4a75870 in codex/actionable-blockers. Preserve the primary checkout. Runtime selection and environment execution already expose typed failures; use them without wiring unqualified graph boundaries or copying open PR61 changes.

## Steps

- [x] Inspect existing failure producers and brainstorm coverage/limits.
- [x] Add runtime guidance and typed setup diagnostics.
- [x] Enforce terminal setup failure and attach trusted diagnostics to final results.
- [x] Add negative trajectory/attribution checks and compare isolated frozen evaluation.
- [x] Review, full offline guards, runbook, CURRENT and handoff.

## Validation and progress

Baseline: `UV_PROJECT_ENVIRONMENT=/home/al/git/corsair/.venv make eval AGENT=environment`, run `20261013T111411Z-development-scripted`, clean 16/16 at main 4a75870. Final candidate `20261013T111956Z-development-scripted`, dirty implementation on the same base, clean 16/16. Prompt identity environment-v1 to environment-v2-blockers; frozen dataset unchanged. Mean scripted requests 5.25, tools 3.75, commands 1.75 and output tokens 162.25 unchanged; estimated input tokens 1016.25 to 1088.625 from guidance. These are synthetic observations, not live efficiency/accuracy evidence.

Validation: initial existing affected suite 52 passed; new targeted suite initially 74 passed/1 failed because a framework-only fixture used project.dependencies, which the existing detector does not read. Changed that fixture to an admitted optional-dependency declaration; 75 passed. Final additional halt/output/cleanup cases: 78 passed, one existing SDK deprecation warning. `make test-config`: first 1250 passed; later 1252 passed before the final exit-zero cleanup test was added. That final code/test change is covered by the 78 affected checks. `git diff --check` passed. Record guards run after handoff. No live runtime, provider, Temporal service or network qualification performed.

Review: finalizer refuses ready and unsupported after a halt; missing run references cannot conceal a known failure. Exit-zero native infrastructure failures get trusted citeable diagnostic text. Ordinary successful stderr never triggers failure; unknown delivery takes priority over package-manager text. No raw command/output URLs are copied into guidance. Existing private ledgers still contain originals. The current parser's project.dependencies omission is outside this slice; detection follow-up should cover that separately.

## Decisions and next action

First stop at available deterministic evidence; preserve unknown root cause and raw private receipts. Guidance is operator-owned, no autonomous retries or policy weakening. Implement and validate runtime/environment consumers; document other producer boundaries as follow-up, not implemented coverage.
