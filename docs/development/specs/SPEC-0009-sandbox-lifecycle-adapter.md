---
id: SPEC-0009
kind: spec
title: Sandbox lifecycle adapter
status: accepted
updated: 2026-10-11
related: [PLAN-0011, PLAN-0010]
---

# Sandbox lifecycle adapter

## Goal and scope

First bounded Milestone 2 slice: a vendor-free typed Sandbox lifecycle port and explicit OpenShell create/readiness/delete implementation, with authoritative operator-host receipts. Excludes exec, transfers, arbitrary output, artifact service, agents, PydanticAI, Temporal, production tenancy and concurrency against external administrators.

## Boundaries and design

Native v0.1.3 SandboxClient performs operations, TLS and polling. Operator selects fixed immutable image, native spec/policy/resources, workspace, ownership and protected host receipt directory; workload cannot edit these. Operator admission requires an exclusive workspace and nonreused names. Each create derives a short name from its operation UUID and sets full operation/owner labels. Domain handles retain original sandbox ID, name, workspace and owner. Native objects remain in the adapter.

Persist an exclusive intent before any operation, then a separate result containing elapsed time, delivery/outcome, original identity and native failure detail. Failure to store intent prevents dispatch. An interrupted or failed mutation remains delivery-unknown; no automatic retry. Post-dispatch receipt failure must expose the known handle/result to the operator for reconciliation. Host receipts are not workload mounts. This minimal journal is necessary because the native SDK has no application lifecycle receipt persistence.

Native wait_ready and wait_deleted take explicit operator `LifecycleLimits` (no implicit SDK default) and wait_ready can return Completed; explicitly require Ready and original ID/labels. Native delete is name-based without an expected-ID conditional delete: check identity immediately before dispatch, validate returned ID, use native wait_deleted(expected_sandbox_id), then require absence by get. These checks refuse observed replacements but cannot make delete atomic against an external concurrent replacement. Admission is restricted to an operator-exclusive workspace with unique names; no raw protobuf workaround or stronger guarantee. Deletion receipt confirms API absence only; qualification separately checks original CR/pod/PVC/PV/container tasks and namespace/private/cluster cleanup.

## Acceptance and validation

Offline contract checks cover Completed rejection, original-ID/owner mismatch with no delete, failed/uncertain mutation without retry, before/after dispatch journal failure, and deletion identity mismatch. Live tests use actual native fixed image, Ready/profile/policy controls and full immutable cleanup, three cycles on each of two fresh nodes after actual storage/kernel/CNI admission. Retain elapsed times, explicit SDK method calls, source hashes and all failures. Internal RPC retries/polls, model calls and tokens are unknown/not applicable, not zero. No mocks count as external qualification.

## Decisions and open questions

Both steps explicitly authorized. Primary pinned source e1f3c82caa3ed3b65de22889ae7ef32a774878ef confirms create labels, 300-default readiness, Completed behavior and name-based deletion. Native conditional-delete gap remains an explicit scope limitation. Next slice after this gate is bounded execution/transfers with output and failure contracts; it is not implemented here.
