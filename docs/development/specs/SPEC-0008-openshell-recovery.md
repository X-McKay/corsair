---
id: SPEC-0008
kind: spec
title: Native OpenShell interruptions and limits
status: accepted
updated: 2026-10-11
related: [PLAN-0009, SPEC-0007]
---

# Native OpenShell interruptions and limits

## Goal and scope

Qualify the remaining native [Milestone 1F](../../openshell-milestone.md) on the admitted Linux amd64 tuple: execution timeout, lost client connection, gateway restart, bounded output, a small bounded OOM case and repeated create/cleanup. The user explicitly authorized 1F and assessing closure of native Milestone 1. Production tenancy, application adapters, agents, Temporal, draft merges and external issue closure remain excluded.

## Boundaries and design

Reuse immutable runtime/toolchain artifacts, native SDK/CLI and Kubernetes lifecycle operations. Every fresh node must pass actual storage/kernel/CNI and gateway controls before destructive probes. No policy/TLS/pin/kernel weakening or retries of possible workload side effects. Fixtures have no providers/credentials/network grants. Native identity, original CR/pods/PVC/PVs/container IDs, host-owned receipts and bounded command/resource budgets bind each attempt.

Pinned SDK exec_stream collects output and exposes no maximum-output argument. Use a focused test client that consumes this native stream, retains only an operator-set byte budget, records observed byte/hash facts and closes the native client on overflow. This is qualification evidence logic for a demonstrated native gap, not a production executor. Do not claim native arbitrary-output memory enforcement. Timeout124 is synthetic gateway status; remote completion remains unknown until independently observed. Disconnect/restart cannot imply nonexecution or authorize replay.

## Acceptance and validation

Two independently created clusters must each pass the full matrix. Three fresh normal sandboxes and one OOM sandbox per node establish repeated original-ID create/cleanup. Passing controls require actual execution/output and original process identity. Timeout and client-loss cases retain native delivery/error detail, single-attempt marker and separate original PID/descendant liveness observations and no executing original container task after teardown. Gateway restart targets only the original owned gateway pod, confirms a different replacement UID and restored native TLS/auth/health, retains external evidence, original workload/storage identity and a single dispatch; incomplete delivery stays unknown. Bounded output requires an exact finite control and a separately observed budget-exceeded native stream with retained bytes within the budget and no invented completion. OOM requires actual configured memory limits and original-container native OOMKilled evidence; MemoryError or generic transport failure cannot pass. Every original resource/storage/container-task and private/forward/cluster cleanup must be confirmed.

Run relevant offline guards before live dispatch, preserve every failed attempt/source revision, and audit raw native evidence. Native milestone closure requires honest reconciliation of all mandatory 1A–1F records and supported limits, not installed resources, mocks or version strings.

## Decisions and open questions

Keep current admitted OpenShell 0.1.3/Agent Sandbox 1.0.6/Helm 3.22.0 and runtime lock. Native Python3.12.15 artifact from 1E supplies fixed synthetic processes. Normal memory512Mi; OOM memory128Mi with a finite maximum 192Mi allocation. The two unchanged-source live matrices now qualify the bounded behavior in [the report](../../qualification/openshell-recovery.md). ISSUE-0004 records variable startup latency with unknown cause; missing our historical 120-second budget does not establish an upstream defect. Future native sandbox-readiness calls use SandboxClient.wait_ready without a timeout override, giving the pinned API's 300-second default. Actual Ready identity and all security/cleanup checks remain mandatory. This is a bounded wait, not a startup SLO. The accepted historical matrices used the earlier 120-second override; the corrected harness has no new live baseline. See [PLAN-0009](../plans/PLAN-0009-openshell-recovery.md).
