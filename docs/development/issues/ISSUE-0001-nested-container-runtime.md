---
id: ISSUE-0001
kind: issue
title: Nested container runtime blocks kind qualification
status: open
updated: 2026-10-10
related: [SPEC-0001, PLAN-0001, IDEA-0001, HANDOFF-0001]
---

# Nested container runtime blocks kind qualification

## Observed and expected behavior

Failure layer: host/kubelet/containerd, before Calico or OpenShell. Kubelet cannot open missing `/dev/kmsg`; after diagnostic restoration of the real device entry inside the owned privileged node, containerd cannot mount its nested overlay rootfs. Expected: Kubernetes static pods start and the native platform/CNI tests can run. [PLAN-0001](../plans/PLAN-0001-local-platform-qualification.md) remains blocked.

## Reproduction and evidence

At baseline commit `047e0bf5dac888f0bbe64c03e24a3e9e09b66397`, run `make tools`, `make test-config`, then `make kind-up` on the recorded Linux amd64 host (Docker 28.4.0, kernel 6.18.44, outer `vfs` storage). Kind control-plane initialization fails; its admin ClusterRoleBinding error is a downstream symptom. Exact commands, messages, timings and private evidence references are in the [qualification report](../../qualification/network-platform.md).

## Attempts and diagnosis

The real 1:11 character-device entry was restored only inside the diagnostic node; no synthetic substitute or policy weakening was used. This exposed the overlay mount failure. The node was then deleted with identity/absence confirmation. No change to the host or automatic bootstrap repair was retained. CNI enforcement, actual OpenShell kernel admission and alternate snapshotters remain unqualified.

## Resolution criteria and next action

Use a compatible Linux Docker host or separately reviewed supported profile. Require all three live checks, confirmed fixture cleanup, then a second clean cluster/run and reviewed evidence. Preserve the failed attempt and qualify the selected runtime rather than counting a patched/reused node as fresh acceptance. Resolve this issue only when that evidence exists. No external issue has been created.
