---
id: PLAN-0103
kind: plan
title: CLI presentation, JSON and direct lifecycle receipts
status: in_progress
updated: 2026-10-14
related: [SPEC-0082]
---

# CLI presentation, JSON and direct lifecycle receipts

## Scope and boundaries

Use a thin native Rich adapter with terminal-only animation, scrolling stderr, NO_COLOR, recorded per-agent telemetry, explicit versioned JSON and honest direct-cancellation receipts. Reject invalid root records; do not alter probe/disposition, OpenShell or Temporal remote-cancellation semantics.

This independent draft PR is based on develop integration snapshot `06d4cbe21b891051811f80559a478881c061ee86`. Other audit changes live in separate PRs, not prerequisites of this branch. The central source-backed audit/HANDOFF-0137 will be delivered in a separate documentation PR; this branch carries its own scoped record and current-work entry.

## Implementation and validation

Implementation is copied from the independently reviewed, reconciled integration worktree; native Temporal fixtures and all seven scripted evaluators passed there, but that does not replace standalone validation. Run `uv sync --locked --group dev`, focused tests, four-worker/serial full suites, final cleanup and re-test. Record actual results below before delivery.

Unrun/unknown: production provider accuracy, Docker/kind/gateway policy and native platform qualification, true backend end-to-end dispositions and native Claude/Codex client compliance. No baselines/prompts are promoted and no production service is deployed.

## Next action

Complete standalone validation and publish this draft for independent review. Do not merge automatically. Preserve failed evidence and explicit unknowns; follow current gate/coordinator decisions for any later live run.
