---
id: PLAN-0004
kind: plan
title: Qualify OpenShell gateway and generated identity
status: complete
updated: 2026-10-11
related: [SPEC-0004, PLAN-0003, HANDOFF-0005]
---

# Qualify OpenShell gateway and generated identity

## Objective and dependencies

Implement only [SPEC-0004](../specs/SPEC-0004-openshell-gateway-identity.md). Source/base 153ed1ee58a3a17b6ee941c12c14da74dfa7276e; clean branch codex/openshell-1b-gateway-identity. Prior admission receipts were re-read: both native reports qualified, ABI 6 and all controls true, separate immutable identities and namespace/PV cleanup confirmed. Remote 1A branch matches published source; draft PR #2 remains separate. No local cluster survived at resume.

## Steps

- [x] Verify source, publication, evidence and current primary releases.
- [x] Pin native CLI and implement explicit native gateway installation/private access setup.
- [x] Run offline guards/render, then fresh cluster prerequisite admission and bounded 1B checks.
- [x] Repeat on a second fresh cluster only if all mandatory boundaries pass; retain failures and identity-checked cleanup.
- [x] Review final diff, qualification report/runbook, CURRENT and new handoff; prepare tracked publication under existing authorization.

## Validation and progress

Primary release API still reports OpenShell v0.1.3, Agent Sandbox v1.0.6 and latest Helm v4.3.0; compatible selected Helm remains 3.22.0. CLI release archive SHA-256 ed08ea7874c47f22d6e5dcc4b27d9ef1ef5d2060f83035b35ff725d5160830a3. Existing artifact/profile source reviewed before edits. First bounded 1B success: .runs/gateway-host-004/, 1 passed in 74.44s, namespace/PVs/private state/port-forward cleanup confirmed. Prerequisite .runs/gateway-prerequisite-001/, 1 passed in 93.84s. Sixteen offline guards/render/compilation pass. Retained failed attempts 001 (HTTP health/gRPC-port mismatch, 11.15s), 002 (native name length rejection, 11.29s), 003 (pod-scope UID assertion vs native container-scope supervisor, 21.84s), all identity-checked cleanup confirmed. None required runtime/security changes. Native host-environment traceback was withheld in private XML; narrow CLI environment and short tracebacks prevent recurrence. One automatic review timeout prevented command launch; single permitted retry succeeded. See the [report](../../qualification/openshell-gateway.md) for identities and full attribution. The runtime lock scope text was clarified after first success; artifact/security inputs are unchanged and the host comparison receipt .runs/gateway-lock-equivalence.json retains that equivalence. Affected network regression passed three tests in 155.19s with both namespace cleanups; first cluster container identity/absence confirmed. Second clean cluster bootstrap passed (.runs/bootstrap/4024779f924a49fa9e0268ee5d90355f/); prerequisites installed (.runs/admission-install/8e723470fb0a442884c07ce9db053f59/) and native admission passed again in 93.77s (.runs/gateway-prerequisite-002/), with fixture/PV cleanup. Second native gateway install passed (.runs/gateway-install/9952d33ff37a44b2a4fe1c974eadbdd4/), qualification .runs/gateway-host-005/ passed in 75.58s with native sandbox/namespace/PVs/private-state/port-forward cleanup. First and second runs each retain 59 native command receipts. Final inventory found zero owned fixture/gateway namespaces, Sandbox/PVC/PV resources; second cluster immutable container/absence cleanup confirmed (.runs/bootstrap/f256bfbf8d7f4fc1b8c86f64fbd15587/cleanup.json). Final source hashes match the second live run. Review strengthened pair ambiguity, effective seccomp/privilege and cleanup status guards and source hash attribution; the first retained native metadata satisfies the added identity assertions (.runs/gateway-host-004/review-guard-audit.json), explicitly a record audit. No runtime inputs/requirements changed. Review added a focused synthetic private-export guard proving credentials/diagnostic bytes never enter receipts; this guard qualifies evidence handling only.

## Decisions and next action

Self-review using the Corsair review skill found no unresolved mandatory 1B finding. Added guards cover private-export evidence, effective security context/ambiguity, explicit source attribution and complete cleanup outcomes. Expected duplicate-evidence rejection preserved the old JUnit (.runs/gateway-duplicate-guard.json). No raw logs/private state/credentials are publication artifacts. Resolve the committed work revision through HANDOFF-0006; publish a separate draft PR based on the still-open 1A branch, without merging either PR.

Use native default mTLS with verified server trust and loopback access; do not introduce anonymous auth. Inspect actual resources and preserve private keys exclusively in `.state/`. Any failed mandatory prerequisite blocks dependent checks; independently record/review the result. Native create/delete calls must be reconciled against immutable identity before cleanup or retry.

Next bounded work is 1C native lifecycle/execution/transfers with SDK identity-checked waits. Plan and pin it first; all later slices/adapters/agents/durability remain unqualified.
