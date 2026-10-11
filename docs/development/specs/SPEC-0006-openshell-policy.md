---
id: SPEC-0006
kind: spec
title: Native OpenShell filesystem and network policy qualification
status: accepted
updated: 2026-10-11
related: [PLAN-0007, SPEC-0005, ISSUE-0003]
---

# Native OpenShell filesystem and network policy qualification

## Goal and scope

Qualify only [Milestone 1D](../../openshell-milestone.md): effective native filesystem and network enforcement on the pinned single-node Linux amd64 tuple. User authorized proceeding after the 1A–1C status review. Toolchains, recovery, adapters, agents, Temporal and production tenancy are excluded.

## Boundaries and design

Use the official v0.1.3 CLI/SDK/chart/runtime and existing kind/Calico/Agent Sandbox/Helm pins. A tiny operator Dockerfile derives from the immutable upstream Ubuntu workload and adds harmless DAC-readable/DAC-writable canaries outside the workspace plus the already-pinned official curl probe binary and isolated musl libraries. Native Docker build with no network and native kind image load stage it; retain source, image config and containerd manifest identities, and request the immutable manifest reference. No package resolution, copied OpenShell runtime or registry publication. Native musl loader configuration keeps the curl libraries separate from Ubuntu libraries; both policies admit only their exact read-only directory. A private local receipt is an artifact binding, not a runtime pass.

Native CLI create and SDK exec/delete/expected-ID wait remain the supported workload paths. Two sequential sandboxes use the same image: a canary control and a restrictive policy. Static filesystem changes require recreation. Runtime policy replacement uses supported CLI set --wait and full/base/global inspection, no providers or credentials. The existing pinned echo fixture supplies unique markers and trusted GET/POST controls. Network rules grant only its exact DNS hostname, port and Service /32 for the canonical curl executable, with REST enforce; narrowing removes POST, then the endpoint. Literal-IP and direct workload routes must be denied. No TLS bypass, wildcard grants or kernel relaxation.

Every fresh node requires real storage/kernel/CNI admission and gateway/identity controls. Preserve native errors and unknown delivery without replay. Compare original sandbox/CR/pod/PVC/PV/namespace identities before cleanup; fixture teardown and gateway/cluster cleanup are part of qualification.

## Acceptance and validation

Control canaries succeed with exact bytes under permitted paths; restrictive sandbox allows scratch read/write, rejects write to the world-writable read-only canary, rejects reading the existing world-readable excluded canary and a scratch symlink to it. Retain trusted image permissions/content and before/after control evidence. Missing files or normal DAC errors cannot establish enforcement.

Network GET and POST must succeed with marker coverage before narrowing; GET remains successful while POST is rejected with native policy detail and no server marker. Removing the endpoint denies GET; literal-IP access and direct pod route cannot bypass. Capture effective policy/revisions and actual generated NetworkPolicies. Fresh trusted controls bracket denial windows; missing positive log coverage fails closed. Repeat the complete matrix three times in fresh control/restrictive sandboxes on each of two fresh clusters, with confirmed cleanup, retaining every failed attempt. Offline failure guards precede live dispatch; they never qualify enforcement. Measure host calls/latency; internal retries and telemetry gaps remain unknown.

## Decisions and open questions

Native v0.1.3 supports exact internal hostnames and allowed_ips /32 with REST inspection over plaintext HTTP; gateway TLS remains verified separately. New local canary artifact is necessary to distinguish Landlock from DAC/absence. Native policy behavior, update activation and transport errors must be established live before claiming the matrix. See [PLAN-0007](../plans/PLAN-0007-openshell-policy.md).
