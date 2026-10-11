---
id: ISSUE-0004
kind: issue
title: Native sandbox admission can exceed the readiness deadline
status: open
updated: 2026-10-11
related: [SPEC-0008, PLAN-0009, ISSUE-0003]
---

# Native sandbox admission can exceed the readiness deadline

## Observed and expected behavior

OpenShell 0.1.3 can acknowledge a native create while its supervisor remains unready past the fixed 120-second SDK wait. This blocks that attempt before recovery workloads. The ordinary-pod Service prerequisite is a separate resolved boundary; no causal identity with ISSUE-0003 is established. A healthy gateway, Ready workload or loaded resources cannot replace native sandbox readiness.

## Reproduction and evidence

The selected immutable Linux amd64 runtime passed real storage/kernel admission and all three CNI controls. During `make qualify-recovery`, recovery-host-002 and final-source recovery-host-009 exceeded 120s. Their original native IDs, SDK errors, partial-admission CR/pod/PVC/PV/container identities and supervisor logs remain under ignored .runs/recovery-resume/ and the native run directories. [The reviewed report](../../qualification/openshell-recovery.md) carries attribution and cleanup. Earlier policy creates near140–142s used a different unchanged180-second native CLI budget; that does not authorize extending this SDK deadline.

## Attempts and diagnosis

Native logs for run 009 show supervision starting but no gateway policy-fetch message before the deadline. Immutable upstream source performs boundary image-policy discovery before gateway policy fetch. The pinned backend gives DiscoverPolicy/Attach a separate five-minute native request budget; this is not authority to extend the local120-second qualification wait. This narrows a possible startup stage; it does not establish the cause, network failure, retry count or a repair. Supported original-ID delete/wait and native resource/container-task cleanup are retained. No unknown workload operation is replayed. Fixture naming, resource serialization, TLS-path and forwarding fixes address separate harness defects and cannot resolve this native issue.

## Resolution criteria and next action

Establish the actual failing startup boundary and a supported bounded remedy, then verify it with attributable native observations and repeated fresh-cluster admission without relaxing policy, TLS, pins, kernel or deadlines. Two successful bounded matrices alone do not prove an admission-reliability repair. Keep this issue open until those criteria pass. PLAN-0009 completed two full final-source matrices on fresh nodes, with confirmed cleanup; this establishes bounded functional behavior without resolving this issue. Failed admission prevents acceptance of its attempt and dependent integration on that runtime. Next separately bounded work is attributable primary-source/native diagnosis; do not apply speculative host/CNI patches or automatic restart workarounds.
