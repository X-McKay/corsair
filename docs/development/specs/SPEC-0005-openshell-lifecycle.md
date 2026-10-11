---
id: SPEC-0005
kind: spec
title: Qualify native OpenShell lifecycle execution and transfers
status: accepted
updated: 2026-10-11
related: [PLAN-0005, SPEC-0004]
---

# Qualify native OpenShell lifecycle execution and transfers

## Goal and scope

Admit only milestone 1C from [the runtime milestone](../../openshell-milestone.md): matching pinned native Python SDK create/get/Ready/exec/delete/wait and CLI upload/download, on the previously admitted local tuple. No application port/adapter, policy 1D, toolchain, interruption/recovery, agents or Temporal integration.

## Boundaries and design

Explicit default workspace and unique names, one active sandbox, existing inert operator-owned hard-Landlock/no-network policy and pinned Ubuntu workload. Native generated protobuf spec types stay inside qualification code; no policy DSL or protocol implementation. Use verified private mTLS and loopback forward through the existing native gateway qualification fixture. Mandatory storage/kernel and current gateway/identity controls pass before lifecycle execution. Credentials remain only in private operator state.

Python 3.12 is compatible with the official v0.1.3 wheel. Its official release SHA-256 is d1eaa6abcd714e2f19d4a8ecbc2079bebeb7b56d81e9f8d3f5a9b5165ed1956c; native uv lock owns matching URL/hash and transitive artifacts. Curated SandboxClient lacks transfers; use supported CLI transfer commands rather than a wrapper or kubectl fallback. Native SDK wait_ready can return Completed: require actual Ready and matching ID. Native expected-ID wait_deleted treats replacement as original deletion; independently assert workspace empty and actual CR/pod identity disappearance. Native workspace PVC/PVs belong to each sandbox and require immutable identity disappearance before the next repetition.

## Acceptance and validation

Small offline pin/spec/receipt guards before live work. On two fresh clusters rerun admission and bounded gateway controls; then three fresh sandbox lifecycle repetitions per cluster. Retain native create/Ready identity and configuration admission, exact separated stdout/stderr and nonzero exit 23, workdir/environment/stdin checks, tiny deterministic binary CLI transfer roundtrip plus SHA-256 from the workload and downloaded bytes, and a read/write roundtrip. Require native deletion acknowledgement ID, supported expected-ID wait and actual per-sandbox CR/pod cleanup before another repetition; per-sandbox workspace PVC/PV reclamation before the next repetition. Final namespace/PV/private state/port-forward and cluster cleanup require immutable identities.

Host receipts retain SDK operation, nonsecret explicit arguments, timestamp/latency, typed result and structured native errors. Exception/timeout before acknowledgment stays delivery unknown, is not blindly retried, and fails qualification. Record all attempts; workload files alone do not establish receipt authority. Native internal RPC/poll/retry counts remain unknown unless observed; no model telemetry exists in this slice. Repetitions measure correctness/consistency/efficiency for this tiny fixture only, not general policy or fleet reliability.

## Decisions and open questions

User continuation and existing publication authorization select this slice. Native SDK/protobuf source and CLI transfer behavior inspected at immutable e1f3c82caa3ed3b65de22889ae7ef32a774878ef. Latest primary release metadata still selects OpenShell v0.1.3 and Agent Sandbox v1.0.6; compatible Helm remains 3.22.0, not latest 4.3.0. Link actual results in [PLAN-0005](../plans/PLAN-0005-openshell-lifecycle.md).
