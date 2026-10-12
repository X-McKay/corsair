---
id: SPEC-0004
kind: spec
title: OpenShell gateway and identity admission
status: accepted
updated: 2026-10-11
related: [SPEC-0003, PLAN-0004]
---

# OpenShell gateway and identity admission

## Goal and scope

Qualify only [Milestone 1B](../../openshell-milestone.md): the official local gateway, verified native caller access and actual generated supervisor/workload identity and mounts. Remaining 1A admission is qualified separately; repeat it before gateway work on each fresh cluster. Creating one inert native sandbox is necessary to observe generated resources, not full lifecycle/execution/policy qualification. Adapters, agents, Temporal, toolchains, recovery and production tenancy remain excluded.

## Boundaries and design

Use the verified v0.1.3 official chart archive and matching images, Helm 3.22.0 and a checksum-locked native CLI. Preserve discovery preflight, TLS and required kernel facilities. Use default native mTLS authentication, no anonymous override, and an explicitly loopback-bound port-forward. The release's setup prose conflicts with its access-control documentation on mTLS; inspect source and test actual authentication rather than infer a pass. Transport credentials remain in private `.state/`, never command receipts or workloads.

Native Helm/Kubernetes and CLI commands own installation and sandbox creation. No custom protocol or application adapter. Metadata inspection must distinguish supervisor projected ServiceAccount identity and CA-only projection from workload token/secret mounts and protected bootstrap initialization. Missing/unsafe identity, failed admission or missing positive network controls blocks this gate. Native failures and uncertain delivery remain separate from TLS, authentication, policy and cleanup failures.

## Acceptance and validation

Run smallest offline guards/render before live work. Two fresh clusters must pass prerequisite admission, chart readiness, verified native CLI health, trusted TLS plus certificate/hostname rejection controls, authenticated caller acceptance and unauthenticated user denial, workload access isolation with reachable controls, and observed generated image/security/identity/mount boundaries. Retain immutable Sandbox/Pod/PVC/PV/namespace/container identities and cleanup confirmation. Preserve timings, failed attempts and explicit unknown/unrun observations. Installation and renders alone cannot qualify 1B.

## Decisions and open questions

The user's continuation authorizes this bounded slice and tracked publication. Prefer default mTLS supported by source over local anonymous access. The generated resources and admission/network controls must determine whether the release can pass; do not modify policy, TLS, image pins or kernel requirements to obtain success. See [PLAN-0004](../plans/PLAN-0004-openshell-gateway-identity.md).
