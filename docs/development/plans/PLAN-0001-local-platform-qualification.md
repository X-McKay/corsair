---
id: PLAN-0001
kind: plan
title: Local platform qualification
status: blocked
updated: 2026-10-10
related: [SPEC-0001, ISSUE-0001, IDEA-0001, HANDOFF-0001, HANDOFF-0003]
---

# Local platform qualification

## Objective and dependencies

Complete the first native platform subset of Milestone 1 before OpenShell installation. [SPEC-0001](../specs/SPEC-0001-local-platform-qualification.md) records scope. This development host cannot run the nested Kubernetes static-pod sandboxes; [ISSUE-0001](../issues/ISSUE-0001-nested-container-runtime.md) blocks live admission. Docs, supported-host research and offline fixes can continue independently.

## Steps

- [x] Pin tools/node/CNI/fixtures and implement explicit owned bootstrap/cleanup.
- [x] Add isolated ingress/egress fixtures, command receipts and identity guards.
- [x] Pass offline configuration checks and native manifest rendering.
- [x] Attempt live bootstrap, retain failure diagnostics, and confirm cluster cleanup.
- [ ] Run all three live checks on a compatible host with confirmed fixture cleanup.
- [ ] Repeat from a second clean cluster; update qualification with actual evidence.
- [ ] Only then extend 1A to actual OpenShell kernel/storage admission and gateway work.

## Validation and progress

Baseline implementation commit: `047e0bf5dac888f0bbe64c03e24a3e9e09b66397`. Original six offline checks pass; Kustomize renders four fixture and 38 Calico resources with pinned images. `make kind-up` fails before CNI installation; `make qualify-network` reports three prerequisite errors and no passing/skipped checks. Native cleanup confirms the owned node is absent. See the [reviewed report](../../qualification/network-platform.md) for exact tuple, timings and evidence identifiers. New development guards do not change this runtime outcome.

## Decisions and next action

No fake kernel device, policy weakening or undocumented patch stack is admitted. Next: use a compatible Linux Docker host and the existing commands, preserving every attempt. Review an explicitly supported alternative profile separately if needed; do not treat it as an automatic fallback.

[HANDOFF-0003](../handoffs/HANDOFF-0003-openshell-continuation.md) records recommended host capacity, upstream kernel/runtime requirements, read-only preflight and the two-clean-cluster procedure. This documentation does not resolve the live blocker. `make test-config` passes all ten offline guards for the handoff update; live Docker qualification was not rerun for this documentation-only change.
