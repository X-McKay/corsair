---
id: PLAN-0102
kind: plan
title: Evaluation accounting and declared policy scope
status: complete
updated: 2026-10-14
related: [SPEC-0082]
---

# Evaluation accounting and declared policy scope

## Scope and boundaries

PR #174 distinguishes task/evaluator completion from conditional semantic accuracy and respects declared release-policy set/mode. Preserve native wall_s/tokens/retries/parameter fields, frozen policies/datasets, current D18 behavior and deferred promotion. This branch is independent of PRs #175/#176; the closed audit/roadmap PR #178 is not a dependency and is not pursued.

## Review follow-up

Rebased onto inspected develop `a00bbbc96d3b97838398693dea3dcae7c43da6bb` after #179/#182/#183, preserving their changes. Address the owner's 2026-10-14 review:

1. Document the additive `completion` block and legacy baseline compatibility below.
2. Keep exactly one PR #174 row inside the CURRENT.md index table; preserve current corpus counts and other rows.
3. Name/comment the legacy task-failure count. Its overlap with `unknown_failures` is intentional only for old receipts; it is not evidence of attributable task failure or completion.
4. Test comparison against an old committed summary without a completion block; report unknown rather than inferring completion from clean-attempt or accuracy counts.
5. Re-run focused and full checks on this branch, then cleanup/re-test and update the existing PR. Do not merge automatically.

## Baseline compatibility

`completion` is additive within `corsair-eval-summary/v1`. Live baselines committed before this merge have **no `completion` field**. They remain readable and unchanged; do not backfill them or infer zero/full completion. `compare` treats absent completion in the selected reference rollup as **unknown**, while continuing to compare existing accuracy/efficiency fields. A baseline with unattributed completion failures is also unknown. Known completion is shown separately from dimension rates, which remain conditional on evaluated attempts.

Committed baseline promotion still requires an eligible live run; live-only policies remain in scope for those runs. Scripted/out-of-set policies report `not_applicable`. This change does not promote a baseline or enable deferred gates.

## Validation

Earlier independently tested snapshots are historical: bdbb2a91 (1637 passed/113 skipped), be80d47c (1688/113), and 92278eed (1702/113), both serial/four-worker. Private failed/intermediate receipts are retained. Review verification on a00bbbc is recorded below after execution, not inferred from these older counts.

Review follow-up validation completed on the pinned a00bbbc base; commands/results below.

Unrun: production provider accuracy, Docker/kind/OpenShell gateway, representative live/held-out disposition benchmarks and external cleanup. Offline/fixture checks and skips are not native platform/inference qualification. No `.runs/`, `.state/`, credentials, raw private diagnostics or model weights are committed.

## Completed owner-review validation

Base: `a00bbbc96d3b97838398693dea3dcae7c43da6bb`.

| Check | Result |
| --- | --- |
| Focused boundary/configuration tests | 124 passed |
| Four-worker make test-v2 | 1704 passed, 113 skipped |
| Serial make test-v2 | 1704 passed, 113 skipped |
| Diff cleanup and focused re-test | diff check passed; 124 passed |

All seven affected scripted agent/chain commands passed; live-only policies reported not_applicable; no baseline promoted.

An initial new test incorrectly expected the existing Java-misanswer fixture to pass. The fixture intentionally fails semantic correctness while both tasks complete; that test expectation was corrected and the failed receipt retained privately. It was not a production regression.

All owner review items are addressed in this branch. The current PR/plan/index provide the next-session context: inspect source/CI, review the bounded diff and keep live qualification separate. PR #178 remains closed and no audit/roadmap continuation is part of this follow-up. Do not merge or promote automatically.
