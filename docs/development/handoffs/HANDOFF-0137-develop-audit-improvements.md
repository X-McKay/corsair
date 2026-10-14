---
id: HANDOFF-0137
kind: handoff
title: Develop audit and bounded quality improvements
status: recorded
updated: 2026-10-14
related: [PLAN-0101, SPEC-0082, PLAN-0099, SPEC-0083]
---

# Develop audit and bounded quality improvements

## Verified state

Branch: `audit/develop-quality-20261014`. The source audit/initial Qwen experiment started at `bc3c25fa46686bdf3120b96caac174c39c8285af`; the code patch was rebased onto `develop` integration snapshot `06d4cbe21b891051811f80559a478881c061ee86`. Resolve the final delivered commit with Git; do not substitute an invented future SHA. The [complete source-backed audit](../../audits/2026-10-14-develop-audit.md) records the moving-branch update and library-pin/documentation limits.

The user requested independently reviewable PRs. `audit/develop-eval-quality-20261014` (PLAN-0102), `audit/develop-cli-quality-20261014` (PLAN-0103) and `audit/develop-skills-quality-20261014` (PLAN-0104) are each based on `06d4cbe`, with isolated source, plans/current entries and standalone tests. `audit/develop-audit-report-20261014` is documentation-only and carries this handoff/PLAN-0101/report. The original combined branch is retained locally for the reviewed source archive, not published as a monolithic PR. No PR is merged automatically.

Delivered: native Rich CLI stage presentation and recorded telemetry; explicit JSON with an honest direct-cancellation envelope; invalid root-record rejection; additive lifecycle receipts; task/evaluator completion coverage and declared release-policy scope; restored `make test-config`; five current canonical developer skills with Codex symlink discovery. No probe/disposition, normal provider, frozen case, policy threshold, promotion, backend-selection or native SDK authority was changed by the audit patch. Upstream Reviewer 157-case evals, D3 re-check loop, OpenShell port/backend and metric naming were preserved, not credited to this patch.

## Validation and blockers

- Original baseline: **1484 passed, 50 skipped**. Independently reviewed pre-rebase patch: **1511 passed, 50 skipped**, both serial/four-worker. The initial wrong-scope chain assertion and empty cancelled-JSON stdout reproduction were retained as private failed attempts, then corrected.
- Final reconciled focused suite: **152 passed**. `TEST_WORKERS=4 make test-v2`: **1649 passed, 113 skipped (54.90s)**. `TEST_WORKERS=0 make test-v2`: **1649 passed, 113 skipped (131.46s)**. Native Temporal test-server tests ran with deterministic stage/model fixtures; skips are not qualification.
- Final scripted evaluator commands: Grounding **85/85**, Investigator **91/91**, Builder **57/57**, Control Prober **65/65**, Exploit Prober **70/70**, Reviewer **157/157**, chain **100/100** clean. Live-only policies report `not_applicable`; no baselines were promoted. These are oracle/plumbing checks, not native execution or inference accuracy.
- Actual all-local SIGINT: one versioned JSON object, persisted `cancelled`, `verdict: null`, null aggregate totals, exit **130**. No external completion, cleanup or resumability is implied.
- Separate official Qwen3-1.7B Q8_0 / llama.cpp b11612 preflight passed. All four 180-second Investigator episodes at the starting snapshot timed out without a final plan; partial usage is a lower bound, full accuracy/cost unknown. No agent prompt changed. The temporary loopback server is stopped; model/binary identities and private transcripts are packaged outside Git.
- **Unrun:** Docker/kind/OpenShell gateway policy/admission, actual backend parity and cleanup, production per-operation Temporal crash/retry/storage, representative live/held-out benchmarks and native Claude/Codex compliance. SDK 0.1.3 source does not certify 0.1.4 APIs or live enforcement.

## Decisions and next steps

[PLAN-0101](../plans/PLAN-0101-develop-audit-improvements.md) is complete for its scope; this is a draft review, not authorization to merge or deploy. Main remains untouched. Preserve concurrent work and current gate/coordinator decisions.

Next independent component: build on Reviewer’s newly frozen set with cited/bounded negative evidence and counterfactual validity, or formalize per-language paired metrics/cohort identity. Do not call synthetic oracle replay a live disposition baseline. Independently admit licensed native vulnerable/fixed pairs before scoring generalized accuracy. Temporal adoption needs an explicit per-operation-versus-stage retry/artifact decision; do not wrap effects in broad retry loops.

For SPEC-0083/OpenShell, native lifecycle/exec are already reused. Remaining P1s: propagate `destroy()` confirmation, require the original native generation/id even if local state is lost, and qualify exact filesystem/process readback. The 0.1.3 wheel has no policy-management/file-transfer API to replace the presently justified CLI/tar seams. Follow the live exec-user/gateway facts and coordinator handover rather than upgrading from newer documentation by assumption.

## Continuation prompt

```text
Read AGENTS.md, docs/development/CURRENT.md, PLAN-0101, this handoff and the audit's moving-branch update. Inspect branch/source and verify the active gate; preserve the upstream OpenShell/Reviewer/D3 work. Use the Corsair development skill. Choose one bounded next component: Reviewer negative-evidence/counterfactual validity with frozen evaluator checks, or explicit paired per-language live metric/cohort semantics. Reuse native PydanticAI/Pydantic Evals; retain failed attempts, unknown telemetry and grouped holdout discipline. Do not infer native execution from fixtures or run a coordinator-owned gateway without handover. Run focused tests, affected scripted suites and serial/fixed-parallel checks as needed, clean up/re-test, update living records/CURRENT.md and append a new handoff.
```
