---
id: PLAN-0101
kind: plan
title: Develop audit improvements
status: complete
updated: 2026-10-14
related: [SPEC-0082, PLAN-0097, PLAN-0099, SPEC-0083, HANDOFF-0137]
---

# Develop audit improvements

## Objective and dependencies

Audit `develop` at `bc3c25fa46686bdf3120b96caac174c39c8285af` against PydanticAI/Harness, Temporal, OpenShell, evaluation and Claude/Codex documentation. Carry a bounded CLI, evaluation-accounting and developer-golden-path patch on `audit/develop-quality-20261014`. No disposition/probe semantics, operator provider policy, frozen datasets or production services are changed by this patch.

While the audit ran, `develop` advanced to `06d4cbe21b891051811f80559a478881c061ee86`: Reviewer evals, D3 re-checking, OpenShell and new metric/provenance names landed upstream. The patch was safely rebased onto that integration snapshot, preserving the upstream work and OpenShell 0.1.3 pin. This plan was renumbered from the uncommitted PLAN-0100 to avoid the upstream collision. The [audit report](../../audits/2026-10-14-develop-audit.md) separates original findings from current changes; its seven initial research workstreams and a bounded late OpenShell review are source-backed, not live qualification.

## Delivered steps

- [x] Verify instructions/source, install the locked Python 3.12 environment and capture baseline.
- [x] Correct declared policy scope and distinguish task/evaluator completion coverage from conditional semantic quality; retain historical unknown attribution and deferred policy/promotion behavior.
- [x] Add native Rich presentation over existing callbacks/records, stage starts, scrolling stderr, terminal-only animation, `NO_COLOR`, per-agent recorded telemetry and explicit versioned JSON.
- [x] Reject nonexistent/malformed root comparison records and persist direct cancellation without a verdict, completed timestamp or cleanup claim; JSON cancellation emits one object and exit 130.
- [x] Restore `make test-config`, simplify five shared canonical developer skills and fix current paths/dynamic scorer discovery; preserve Codex symlinks and add structural guards.
- [x] Run separate pinned local Qwen/llama.cpp protocol and prompt-ablation experiments; keep normal HTTPS/vLLM configuration unchanged and do not promote a prompt/baseline.
- [x] Independently review, correct the cancelled-JSON blocker and two skill instructions, reconcile upstream, re-test both topologies and all seven scripted evaluators.
- [x] Complete sanitized report, current index and HANDOFF-0137; package private raw evidence/reproduction scripts separately from Git, and split changes into independent draft PRs for evaluation, CLI, developer skills and documentation (never merge).

## Validation and progress

| Check | Actual outcome | Scope |
| --- | --- | --- |
| Original `TEST_WORKERS=4 make test-v2` | 1484 passed, 50 skipped; 59.92s | Starting snapshot, locked Python 3.12 |
| Initial focused patch check | 167 passed | CLI, records, coverage and configuration |
| Post-review pre-rebase suites | 1511 passed, 50 skipped, serial and four-worker | A formerly wrong-scope chain assertion was corrected; failed attempt retained privately |
| Actual local SIGINT probe | One JSON object, `state=cancelled`, `verdict=null`, exit 130 | Real CLI interrupt with deterministic stages/model doubles; no provider/backend |
| Reconciled focused suite | 152 passed; 20.89s | CLI/coverage/chain/agent-eval/record/configuration |
| Reconciled `TEST_WORKERS=4 make test-v2` | 1649 passed, 113 skipped; 54.90s | Integrated `06d4cbe` plus this patch |
| Reconciled `TEST_WORKERS=0 make test-v2` | 1649 passed, 113 skipped; 131.46s | Same source; serial topology |
| Reconciled scripted evals | Grounding 85/85; Investigator 91/91; Builder 57/57; Control 65/65; Exploit 70/70; Reviewer 157/157; chain 100/100 | Oracle-replay plumbing, not inference/disposition accuracy; all live-only policies `not_applicable`; no promoted baseline |
| Local Qwen preflight | 2 requests, 1 tool call, 494 input/25 output tokens | Pinned Qwen3-1.7B Q8_0, llama.cpp b11612, CPU, loopback |
| Local Investigator ablation | 4/4 timed out at 180s; no final plan | Starting-snapshot Python development cases; conditional accuracy/full episode cost unknown; no prompt promotion |

Existing Temporal test-server workflow tests passed with deterministic stage/model fixtures. No Docker, kind, OpenShell gateway, native platform admission, production per-operation Temporal durability, representative live/held-out disposition accuracy or Claude/Codex client-compliance qualification is claimed. The temporary Qwen server is stopped. Raw `.runs/`, private transcripts, weights and credentials are excluded from Git; the separate audit bundle retains actual failures, identities and measurements.

The user requested independent PRs on 2026-10-14: PLAN-0102 (evaluation accounting), PLAN-0103 (CLI/lifecycle) and PLAN-0104 (developer golden path) each live on a separate branch based on `06d4cbe`. Their standalone validation is recorded in their own plans. This documentation-only PR carries the central report/handoff; it does not bundle the code changes or require another PR to run its checks. The combined source archive is a distinct reviewed integration deliverable.

## Decisions and next action

Reuse argparse, native Rich 15.0.0, native Pydantic Evals and existing record/callback interfaces. The only new renderer is a small presentation adapter; no scheduler, provider protocol, trace parser, Typer/Textual application or second skill registry. Unknown telemetry stays null. Upstream run-record names and OpenShell selection/SDK/authority are preserved.

Prioritize native Temporal retry/artifact boundaries, cited/bounded negative Reviewer evidence and executable counterfactual oracles, statistically defined per-language paired live comparisons, and licensed benchmark admission. For the newly implemented OpenShell backend, carry cleanup confirmation, require generation-bound ownership and qualify exact effective policy before promotion. Follow current SPEC-0083/coordinator gate decisions; do not infer a live pass from source or mocks. See [HANDOFF-0137](../handoffs/HANDOFF-0137-develop-audit-improvements.md) for continuation.

## Final split-base alignment

All independent code/documentation PRs preserve develop `bdbb2a91135f61bb33cd19ec3a4421cf284094f5`, including native live-baseline/commit helpers and D18 source standards. The source audit/initial experiment remain explicitly anchored to their earlier snapshots. No D18 verdict implementation or live baseline promotion is part of this patch. Each branch carries independent final-base validation; the combined archive is separately tested.

## Published independent review units

### Published independent code review units and final integration

| Draft PR | Scope | Standalone serial / four-worker | Post-cleanup focused |
| --- | --- | --- | --- |
| [174](https://github.com/X-McKay/corsair/pull/174) | Evaluation accounting and declared policy scope | 1637 passed, 113 skipped (both) | 20 passed |
| [175](https://github.com/X-McKay/corsair/pull/175) | CLI presentation, JSON and direct lifecycle receipts | 1646 passed, 113 skipped (both) | 29 passed |
| [176](https://github.com/X-McKay/corsair/pull/176) | Shared developer skills and configuration golden path | 1637 passed, 113 skipped (both) | 107 passed |

All are base-aligned to `bdbb2a91135f61bb33cd19ec3a4421cf284094f5`; none is merged. The separate documentation-only PR contains no code from these three areas. Final combined reviewed source: **1658 passed, 113 skipped**, both serial and four-worker; post-cleanup re-test **128 passed**. Documentation configuration checks: **101 passed**. Skips and fixture passes are not native platform or inference/disposition qualification.
