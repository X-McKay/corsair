---
id: PLAN-0011
kind: plan
title: Sandbox lifecycle adapter
status: complete
updated: 2026-10-11
related: [SPEC-0009, PLAN-0010]
---

# Sandbox lifecycle adapter

## Objective and dependencies

Implement only the typed native create/readiness/delete and host receipt boundary in SPEC-0009. Native 1A–1F historical qualification is verified; the first-node native readiness sample passed before live adapter work. Policies, pins, TLS, storage/kernel requirements and resource budgets remain operator-owned.

## Steps

- [x] Implement narrow vendor-free port and OpenShell adapter using supported native methods and immutable handles; persist host intent/results.
- [x] Run meaningful offline negative-path checks and repository guards before live adapter work.
- [x] Qualify three actual cycles on each of two fresh admitted nodes, checking native identity, Ready, profile/policy, receipts and immutable cleanup.
- [x] Review final diff, update qualification/work records and CURRENT, append HANDOFF-0013 and publish tracked authorized changes as a stacked draft.

## Validation and progress

Before editing, inspected native pinned SDK/server source and installed source SHA-256 57b9450b6b514a90f994d03fdb8a2b52d3d23d35560f66e7e2100d09ec7814cb. create/get/delete/wait_ready/wait_deleted supported; conditional expected-ID delete absent. Primary release APIs and source references retained ignored under .runs/lifecycle-adapter-resume. Baseline 94 guards pass. First fresh native readiness sample passed: 142.237/9.015/8.014s with confirmed original-resource and fixture cleanup. Implemented narrow port, immutable operator spec snapshot, protected inode-held host directory, exclusive fsynced intent/results, native identity/Ready checks and original-ID deletion/absence checks. 109 offline checks passed (94 guards+15 contract cases). Adapter-host-001 passed three actual cycles in 123.760s, 36 explicit SDK method observations; waits 8.016/9.017/9.017s. Each forged-ID delete was refused before mutation. Native API absence, original CR/pods/PVC/PV/container task, gateway namespace/PV/private/forward cleanup audited. Empty final inventory and original cluster CID absence confirmed; node 2 repetition subsequently passed with the same source. No live adapter failures in either counted matrix. Source frozen under .runs/lifecycle-adapter-resume/source-v1 and audited against raw per-run manifests.

Pre-publication Corsair review checked actual source against SPEC-0009: vendor objects remain in the adapter, spec inputs are snapshotted, host intent is durable before native dispatch, storage errors retain known handles/native uncertainty, Completed cannot pass readiness, original owner/ID is checked before name-based delete, API-name absence is distinct from Kubernetes/container cleanup, no retries/fallback or new authority. No blocking code finding. Native atomic-delete and live worker/storage-fault coverage remain explicit limitations. Final two-node raw/source/identity review passed; publication follows the reviewed tracked diff.

## Decisions and next action

No retries, fallback, custom transport or concurrency claim. Preserve operation ID and original handle even if result persistence fails. Next bounded component is execution/transfers/output/failure contracts, after its own focused spec and offline checks; current lifecycle code is not full Milestone 2 qualification. Do not begin execution/agent/durable integration.

Final acceptance: both independent fresh-node runs audited against raw receipts and frozen sources; all original resource, namespace/PV/private/forward and cluster IDs confirmed absent. See the reviewed [readiness](../../qualification/openshell-readiness.md) and [adapter](../../qualification/openshell-adapter-lifecycle.md) records. Final offline/diff review, HANDOFF-0013 and tracked stacked-draft publication are the closing session steps; remote exact-head CI is verified after publishing, not claimed as live runtime proof. No execution/transfers/agent/durable work was started.
