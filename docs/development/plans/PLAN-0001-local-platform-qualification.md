---
id: PLAN-0001
kind: plan
title: Local platform qualification
status: complete
updated: 2026-10-11
related: [SPEC-0001, ISSUE-0001, IDEA-0001, HANDOFF-0001, HANDOFF-0003, HANDOFF-0004]
---

# Local platform qualification

## Objective and dependencies

Complete the first native platform subset of Milestone 1 before OpenShell installation. [SPEC-0001](../specs/SPEC-0001-local-platform-qualification.md) records scope. The original development host could not run nested Kubernetes workloads; a compatible host has now passed the required two clean cluster runs and [ISSUE-0001](../issues/ISSUE-0001-nested-container-runtime.md) is resolved for the qualified tuple.

## Steps

- [x] Pin tools/node/CNI/fixtures and implement explicit owned bootstrap/cleanup.
- [x] Add isolated ingress/egress fixtures, command receipts and identity guards.
- [x] Pass offline configuration checks and native manifest rendering.
- [x] Attempt live bootstrap, retain failure diagnostics, and confirm cluster cleanup.
- [x] Run all three live checks on a compatible host with confirmed fixture cleanup.
- [x] Repeat from a second clean cluster; update qualification with actual evidence.
- [x] Confirm identity-checked cluster cleanup and publish the reviewed boundary result.

## Validation and progress

Baseline implementation commit: `047e0bf5dac888f0bbe64c03e24a3e9e09b66397`. Ten offline checks pass. On the qualified host, the first bootstrap exposed a `kind load docker-image` digest-only archive defect and was cleaned up. The bootstrap now leaves the immutable pod references to the node's native CRI pull path. Two subsequent clean clusters passed all three live checks in 156.07 and 155.98 seconds with distinct node identities, confirmed fixture cleanup and confirmed cluster cleanup. See the [reviewed report](../../qualification/network-platform.md) for the exact tuples and evidence identifiers.

## Decisions and next action

No fake kernel device, policy weakening, unpinned image or undocumented runtime patch was admitted. The failed host and failed archive-import attempt remain part of the evidence history. The native CRI pull change is limited to bootstrap image delivery; the deployed references and qualification assertions remain digest-pinned.

[HANDOFF-0004](../handoffs/HANDOFF-0004-kind-calico-qualified.md) records the qualified result and the next bounded action. Select compatible immutable Agent Sandbox, OpenShell, Helm and workload artifacts before extending 1A to supported installation, storage/PVC behavior and actual kernel/runtime admission. Ordinary-pod CNI qualification does not qualify those later boundaries.

The continuation [PLAN-0003](PLAN-0003-openshell-admission.md) completed that bounded remaining 1A prerequisite/storage/native-kernel slice on two fresh clusters; full OpenShell gateway/lifecycle qualification remains separate.
