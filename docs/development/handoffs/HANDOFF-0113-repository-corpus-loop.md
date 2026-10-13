---
id: HANDOFF-0113
kind: handoff
title: Repository-owned corpus improvement loop kickoff
status: recorded
updated: 2026-10-13
related: [PLAN-0087, ISSUE-0008, SPEC-0067, SPEC-0044]
---

# Repository-owned corpus improvement loop kickoff

## Verified state

The user requested that the improvement loop be stored in the repository and merged to main, so a fresh Claude or other agent session can start without a Codex worktree. The canonical procedure is [docs/runbooks/corpus-improvement-loop.md](../../runbooks/corpus-improvement-loop.md), tracked by [PLAN-0087](../plans/PLAN-0087-corpus-baseline-loop.md) and linked from CURRENT and the development guide. This is a documentation-only publication based on main `e84a2bb`. Resolve the final documentation/merge revision from Git.

The earlier unpublished plan used PLAN-0085; main has since assigned that ID to its parallel-offline-suite plan. PLAN-0087 avoids the collision. The local candidate implementation, earlier private receipts and raw model outputs are not included in this publication. Runtime, agent, image and qualification state remain unchanged by this documentation merge.

On the publication base, corpus loader/materializer, isolated evaluations and the Docker product route exist; the finite corpus campaign module and local Node22 candidate do not. Product build still refuses an absent fixed revision. Reconcile pending fixes before implementing duplicate work. Local pilots previously reached planning without an admitted disposition and exposed an environment-directory/planner-file mismatch plus output exhaustion; reproduce from current source. The runbook does not claim a current per-language accuracy score.

## Validation and blockers

Final offline checks: `tests/configuration/test_development_workflow.py` passed 5 tests in 0.69 s; `TERM=xterm TEST_WORKERS=4 make test-config` passed 1,965 tests with one skip and 11 dependency/runtime deprecation warnings in 58.98 s. `git diff --check` passed. These checks used the publication candidate based on main, not the earlier local implementation branch. No new live evaluation, corpus acquisition or model run was performed. No private run/state data, credentials or machine-specific checkout dependencies are published. Links are repository-relative.

Candidate-free product support remains [ISSUE-0008](../issues/ISSUE-0008-fix-free-product-investigation.md) on the inspected main base. Runtime readiness, dependency setup, exact discovery and appropriate effect evidence are separate gates. Historical image controls or passing offline tests cannot prove full product support. The frozen corpus split has 66 development and 16 held-out configurations; Java and C currently have no held-out topics.

## Decisions and next steps

Follow the runbook's measure/diagnose/isolated-compare/Docker-compare/transfer loop. Retain the baseline even when poor. Separate complete-inventory coverage, reviewed-oracle useful accuracy, conclusive-only accuracy, fix correctness and evidence validity. When the existing set consistently passes, inspect coverage gaps and admit two to four independent families with reviewed oracles and fresh holdout; retain old-cohort regression separately.

The immediate implementation objective is complete positive and independent negative Python investigations plus a development transfer case, while another language advances through the full execution/evidence path. Verify available code and resources in the new checkout; provider configuration is supplied through the existing operator-owned mechanism, never through this document. Preserve exactly two finding tests, label isolation, frozen identities and all failure/cleanup receipts. No new scheduler, generic repair engine, blind retry or relaxed security gate.

## Continuation prompt

```text
Continue Corsair's corpus baseline and iterative improvement work from a checkout of main. Read AGENTS.md, README.md, docs/development/CURRENT.md, docs/runbooks/corpus-improvement-loop.md, PLAN-0087, HANDOFF-0113 and ISSUE-0008. Use the repository development/review/handoff skills. Inspect Git status and actual source; preserve unrelated work. Do not assume earlier Codex branches, private receipts or campaign code are present or merged.

Reconcile pending implementations first. Then delegate independent isolated work where available: approved-directory/exact-file contract correction, candidate-free product support, and one complete JavaScript or Perl execution/evidence slice. Prefer Sol workers if supported; otherwise use available agents. Root owns integration, metrics and one initial live Docker/model slot. Reproduce each failure and compare frozen isolated evaluations before composition. Treat output exhaustion as a separate hypothesis.

Work toward a complete positive Python disposition, independent negative and development transfer case. Integrate/verify the finite campaign entry before using it. Freeze candidates and bounded batches, then progress toward the 66-configuration development baseline. Review oracles before claiming accuracy; preserve failed, unsupported, inconclusive, unknown and unstarted cases. Keep labels and verification tests outside agent inputs and exactly two finding-specific tests.

Repeat measure -> diagnose one cause -> bounded change -> isolated comparison -> Docker comparison -> transfer -> retain or accept candidate. When current cases consistently pass with valid evidence, use the runbook's targeted example expansion process, preserve original baselines and reserve fresh held-out families before inspection. No held-out tuning or blind retries. Continue independent work when a dependent gate is blocked.

Existing authorization covers development and delegation; do not ask for routine reconfirmation. Report actual checks and limits, update the plan/CURRENT and write a new handoff. Do not infer authorization for deployment, unrelated merges or scheduled background work.
```
