---
id: IDEA-0001
kind: idea
title: Explicit supported local runtime profiles
status: deferred
updated: 2026-10-10
related: [ISSUE-0001, PLAN-0001]
---

# Explicit supported local runtime profiles

## Problem and evidence

The first nested development host cannot start the selected kind static-pod workloads. Different workstation/VM/container hosts may need separately admitted local prerequisites. See [ISSUE-0001](../issues/ISSUE-0001-nested-container-runtime.md).

## Proposal and limits

If a normal compatible Linux Docker host is insufficient for required local development, research documented kind/containerd profiles and select an explicit pinned profile. Each must pass the same fresh-cluster network, identity, cleanup and later OpenShell kernel checks. Prefer native configuration; no runtime autodetection/fallback service or accumulating patch scripts.

## Decision

Deferred. First rerun the existing slice on a compatible host. This idea is not authorization to change the snapshotter, synthesize kernel facilities, relax policy or expand the supported envelope. A concrete additional host requirement and independently qualified profile would justify a spec/plan later.
