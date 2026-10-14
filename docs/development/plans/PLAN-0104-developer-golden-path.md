---
id: PLAN-0104
kind: plan
title: Shared developer skills and configuration golden path
status: in_progress
updated: 2026-10-14
related: [SPEC-0082]
---

# Shared developer skills and configuration golden path

## Scope and boundaries

Restore make test-config; remove obsolete duplicated v1 architecture from five canonical skills, fix exact current-work paths and verified dynamic scorer discovery, and preserve native Codex symlinks/current qualification authority. Structural guards do not certify model/client compliance.

This independent draft PR is based on develop integration snapshot `06d4cbe21b891051811f80559a478881c061ee86`. Other audit changes live in separate PRs, not prerequisites of this branch. The central source-backed audit/HANDOFF-0137 will be delivered in a separate documentation PR; this branch carries its own scoped record and current-work entry.

## Implementation and validation

Implementation is copied from the independently reviewed, reconciled integration worktree; native Temporal fixtures and all seven scripted evaluators passed there, but that does not replace standalone validation. Run `uv sync --locked --group dev`, focused tests, four-worker/serial full suites, final cleanup and re-test. Record actual results below before delivery.

Unrun/unknown: production provider accuracy, Docker/kind/gateway policy and native platform qualification, true backend end-to-end dispositions and native Claude/Codex client compliance. No baselines/prompts are promoted and no production service is deployed.

## Next action

Complete standalone validation and publish this draft for independent review. Do not merge automatically. Preserve failed evidence and explicit unknowns; follow current gate/coordinator decisions for any later live run.
