---
id: SPEC-0001
kind: spec
title: Local platform qualification
status: accepted
updated: 2026-10-10
related: [PLAN-0001, ISSUE-0001]
---

# Local platform qualification

## Goal and scope

Establish an independently testable kind/Calico boundary before adding OpenShell or agents. This indexes the already-approved initial subset of the [OpenShell milestone](../../openshell-milestone.md); it does not rewrite that contract. Scope is one Linux amd64 control-plane node and trusted ordinary-pod network fixtures. OpenShell admission, storage, multi-node isolation, toolchains and real security issues remain outside this slice.

## Boundaries and design

Use pinned native kind, Kubernetes, Calico, Docker image loading, Kustomize and pytest. Setup is explicit and separate from qualification. Local ownership/kubeconfig state is separate from retained evidence. Reject unknown/replacement resources and silent fallback. Attribute host/bootstrap failures before workload policy is involved.

## Acceptance and validation

Offline guards and native rendering validate configuration only. Real ingress/egress controls must reach a known endpoint, then forbidden fresh connections must time out and be absent from covered server logs. Check both PodIP/Service paths and GET/POST, three trials each, plus policy reversal/narrow allow. Require confirmed cleanup and a second clean cluster creation/run before admitting the live CNI boundary.

## Decisions and open questions

The selected tuple and current blocked outcome are in the [qualification record](../../qualification/network-platform.md). User authorization established progressive native qualification before adapters. [ISSUE-0001](../issues/ISSUE-0001-nested-container-runtime.md) must be resolved with actual live evidence before this boundary is qualified.
