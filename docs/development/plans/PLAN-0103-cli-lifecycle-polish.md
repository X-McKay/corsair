---
id: PLAN-0103
kind: plan
title: CLI presentation, JSON and direct lifecycle receipts
status: complete
updated: 2026-10-14
related: [SPEC-0082]
---

# CLI presentation, JSON and direct lifecycle receipts

## Scope and boundaries

Use a thin native Rich adapter with terminal-only animation, scrolling stderr, NO_COLOR, recorded per-agent telemetry, explicit versioned JSON and honest direct-cancellation receipts. Reject invalid root records; do not alter probe/disposition, OpenShell or Temporal remote-cancellation semantics.

This independent draft PR is based on develop integration snapshot `bdbb2a91135f61bb33cd19ec3a4421cf284094f5`. Other audit changes live in separate PRs, not prerequisites of this branch. The central source-backed audit/HANDOFF-0137 will be delivered in a separate documentation PR; this branch carries its own scoped record and current-work entry.

## Implementation and validation

Implementation is copied from the independently reviewed, reconciled integration worktree; native Temporal fixtures and all seven scripted evaluators passed there, but that does not replace standalone validation. Run `uv sync --locked --group dev`, focused tests, four-worker/serial full suites, final cleanup and re-test. Record actual results below before delivery.

Unrun/unknown: production provider accuracy, Docker/kind/gateway policy and native platform qualification, true backend end-to-end dispositions and native Claude/Codex client compliance. No baselines/prompts are promoted and no production service is deployed.

## Next action

Complete standalone validation and publish this draft for independent review. Do not merge automatically. Preserve failed evidence and explicit unknowns; follow current gate/coordinator decisions for any later live run.

## Final standalone evidence

Final base `bdbb2a91135f61bb33cd19ec3a4421cf284094f5` preserves D18 source standards and native live-baseline/commit helpers. The original `06d4cbe` checks remain private history; no D18 verdict implementation is included here.

| Check | Passed | Skipped |
| --- | --- | --- |
| Focused | 29 | 0 |
| Four-worker full suite | 1646 | 113 |
| Serial full suite | 1646 | 113 |
| Post-cleanup focused re-test | 29 | 0 |

Final diff cleanup check passed. Whole-chain scripted evaluation passed 100/100; no baseline promoted. Skipped tests are not native qualification. Production models, Docker/kind/gateway, backend end-to-end dispositions and held-out accuracy remain unrun. No private `.runs/`, `.state/`, credentials, raw logs or weights are committed.
