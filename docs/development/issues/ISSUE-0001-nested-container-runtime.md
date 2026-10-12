---
id: ISSUE-0001
kind: issue
title: Nested container runtime blocks kind qualification
status: resolved
updated: 2026-10-11
related: [SPEC-0001, PLAN-0001, IDEA-0001, HANDOFF-0001, HANDOFF-0003, HANDOFF-0004]
---

# Nested container runtime blocks kind qualification

## Observed and expected behavior

Original failure layer: host/kubelet/containerd, before Calico or OpenShell. Kubelet could not open missing `/dev/kmsg`; after diagnostic restoration of the real device entry inside the owned privileged node, containerd could not mount its nested overlay rootfs. Expected: Kubernetes static pods start and the native platform/CNI tests can run. This remains an unsupported-host result, but [PLAN-0001](../plans/PLAN-0001-local-platform-qualification.md) is complete on a separately qualified tuple.

## Reproduction and evidence

At baseline commit `047e0bf5dac888f0bbe64c03e24a3e9e09b66397`, run `make tools`, `make test-config`, then `make kind-up` on the recorded Linux amd64 host (Docker 28.4.0, kernel 6.18.44, outer `vfs` storage). Kind control-plane initialization fails; its admin ClusterRoleBinding error is a downstream symptom. Exact commands, messages, timings and private evidence references are in the [qualification report](../../qualification/network-platform.md).

## Attempts and diagnosis

The real 1:11 character-device entry was restored only inside the diagnostic node; no synthetic substitute or policy weakening was used. This exposed the overlay mount failure. The node was then deleted with identity/absence confirmation. No change to the host or automatic bootstrap repair was retained. CNI enforcement, actual OpenShell kernel admission and alternate snapshotters remain unqualified.

## Resolution criteria and next action

Resolution evidence exists on Ubuntu 24.04.5 LTS, Linux `6.14.0-37-generic`, Docker `29.8.2`, `overlay2`, cgroup v2, with a real `/dev/kmsg`. After correcting digest-only image delivery to use the node's native CRI pull path, all three live checks passed on two fresh clusters in 156.07 and 155.98 seconds. The runs used distinct node UIDs; all four fixture namespace cleanups and both immutable-identity cluster cleanups were confirmed. No external Corsair issue was created.

The reviewed [qualification report](../../qualification/network-platform.md) preserves both failed-host history and the successful evidence identifiers. This resolves the ordinary-pod kind/Calico blocker only. The subsequent [remaining 1A admission record](../../qualification/openshell-admission.md) separately qualifies native OpenShell kernel primitives and local-path storage. Gateway/identity and full lifecycle remain unqualified; this issue's resolution still covers only the ordinary-pod blocker.
