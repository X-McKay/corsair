---
id: SPEC-0017
kind: spec
title: Bounded untrusted test report consumer
status: accepted
updated: 2026-10-12
related: [PLAN-0019, SPEC-0010, SPEC-0012]
---

# Bounded untrusted test report consumer

## Goal and scope

Implement one concrete machine-readable test-observation report over the existing qualified bounded execution stdout and immutable artifact ports. User authorization to proceed with all four priorities includes this small consumer. It supports the [investigation contract](../../investigation-contract.md)'s exactly two finding-specific tests without treating a workload-authored claim as semantic attestation. This slice does not execute tests, generate tests, extract archives, fetch paths, assess evidence, verify a fix or admit general transfers/reconciliation.

## Boundaries and design

The operator supplies an expected execution operation/handle, source and frozen-test artifact references, and the admitted stdout artifact reference. The consumer requires an acknowledged terminal receipt, confirmed worker cleanup, no receipt-storage failure, and native exit0 or1. It reads at most4096 bytes through the existing artifact port and binds the exact artifact bytes/hash/size to receipt stdout. No workload-provided artifact path or URL is followed.

The versioned UTF8 JSON payload contains only schema_version, operation, source_sha256, tests_sha256 and two named claims: control/security, each with a bounded unique test_id and passed/failed/skipped outcome. Reject duplicate JSON keys, unknown fields/versions, noncanonical identifiers, excessive size, malformed encodings, scope/identity mismatch and extra conclusions. Output retains the trusted source/test/operation/handle/artifact identities and untrusted typed claims. It grants no finding/fix disposition. Skipped or failed controls remain explicit claims; they cannot establish safety or a fix. Native exit consistency is checked for completed test claims; a skipped report remains nonconclusive regardless of exit.

Pydantic performs finite schema validation; standard JSON duplicate-key rejection fills its default last-key-wins behavior. This is an application-specific format, not a custom test runner or replacement for native pytest/JUnit. A later native runner adapter must establish real discovery and test semantics separately.

## Acceptance and validation

Use the actual LocalArtifacts implementation in host tests, immutable references and distinct operation identities. Cover success, failed security assertion/exit1, failed/skipped control retained without disposition; reject fabricated fix fields, duplicate keys, malformed/oversized/corrupt bytes, identity mismatch, incomplete execution and inconsistent exit. A fresh host process must reread and consume retained immutable bytes. Host tests qualify parsing/composition only. Separately, on each of two fresh mandatory-admitted OpenShell nodes, a fixed inert producer emits literal reports with native exits0/1; the actual execution stdout is stored and consumed through existing ports, then reread after original sandbox cleanup. This qualifies native report-byte composition, not application test discovery/validity or any finding/fix conclusion. Preserve before-live source/test/lock freezes and original sandbox/gateway/cluster cleanup.

## Decisions and open questions

A workload JSON claim is deliberately separated from trusted execution metadata. The smallest initial format excludes arbitrary prose/HTML, attachments and dynamic schema selection. A later application producer can emit this format after actual two-test discovery; that is a separate boundary, not established by the inert native producer. General OpenShell ISSUE-0006 remains unresolved.
