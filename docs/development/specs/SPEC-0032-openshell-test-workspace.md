---
id: SPEC-0032
kind: spec
title: OpenShell test workspace adapter
status: draft
updated: 2026-10-12
related: [SPEC-0011, SPEC-0018, SPEC-0025, SPEC-0027, SPEC-0028, PLAN-0027, PLAN-0032, ISSUE-0006]
---

# OpenShell test workspace adapter

## Goal and scope

[SPEC-0028](SPEC-0028-test-authoring-agent.md) left the `TestWorkspace` port without a sandbox implementation, so agent-written tests could only run through a stand-in. This adapter prepares a fresh OpenShell sandbox holding one captured source revision plus exactly one `ApprovedPatch` at a fixed in-sandbox root, so the existing `PytestRunner` runs discovery and the two tests there and returns the unchanged `NativeTestRun` shape with repository-relative node ids.

In scope: small fixture trees delivered by the already qualified fixed source-arrival recipe ([SPEC-0011](SPEC-0011-native-transfer-admission.md), [source-arrival report](../../qualification/openshell-source-upload.md)). Excluded: general source delivery (the [SPEC-0025](SPEC-0025-sandbox-source-fetch.md) in-sandbox fetch stays blocked on a qualified storage quota and the credential placeholder check), dependency setup, post-execution integrity, any witness capture, durable registration and connection to the authoring agent or the fixture chain.

## Boundaries and design

**Ports reused.** `OpenShellTestWorkspace` composes the existing `SandboxLifecycle`, `SandboxExecution` and `ArtifactStore` ports with a narrow `DirectoryUpload` port. One instance serves one captured `SourceSnapshot`; each `prepare(patch, operation)` creates its own sandbox, and `release` deletes it. Operation ids for create, ready, the two verifier executions, upload and discard or release derive from the run operation with `uuid5`, so receipts stay attributable to one run.

**Delivery.** The curated SDK has no transfer methods ([ISSUE-0006](../issues/ISSUE-0006-native-transfer-retry-admission.md)), so `CliUpload` runs the pinned `openshell sandbox upload --no-git-ignore` once against a private host staging copy, rechecking the binary's SHA256 before dispatch and journaling intent and result. The CLI's own whole-operation retries remain; the adapter adds none. A nonzero exit, timeout or launch error is unknown delivery, and the sandbox is discarded rather than repaired. Staging holds source files at 0400/0500 from the immutable store and patch files at 0400 under 0700 directories, and is removed once the CLI has exited; the authoritative bytes stay in the store.

**Admission.** A fixed operator verifier runs through the existing execution adapter before and after upload. It reads, never imports, workspace content and reports the root and every entry: type, mode, owner, link count, size and SHA256. The host requires the root absent before upload and afterwards an exact match with the captured snapshot plus the patch: same paths, modes, owner, single links, sizes and digests, only the expected 0700 directories, no symlink or other entry and no truncation. The patch may not overlap captured source, and the tree is bounded to 64 entries and 4 MiB, matching the qualified arrival envelope. As in SPEC-0025, the values come from inside the sandbox before any repository code has run; once tests execute, the working copy is untrusted.

**Results.** `prepare` returns `PreparedWorkspace{handle, source: snapshot manifest, tests: patch manifest, patch_sha256}`. The patch manifest lists each file's path, size and digest (each file's bytes are stored too), so `AdmittedTestClaims` bind to stored source and test identities. Refusals raise `WorkspaceError{layer: staging | sandbox | upload | admission, cleanup}`; after a handle exists every refusal deletes the sandbox and reports confirmed or unconfirmed cleanup, and a failed create without a handle stays unconfirmed. The runner already maps a preparation exception to its `workspace` failure layer with unconfirmed cleanup.

**Runner placement.** The operator wires a second execution adapter whose workdir is the remote root and passes the same root as `PytestRunnerConfig.workspace_root`, which keeps node ids and failure frames repository-relative. The runner's wrapper now starts `/bin/sh` by absolute path, because sandbox execution does not promise a `PATH` lookup.

**Witness telemetry (recorded only).** Nothing here produces a witness. Sources the execution node could later own outside the test process: OpenShell policy decision and denial events for filesystem and network access (already observed in [SPEC-0006](SPEC-0006-openshell-policy.md) qualification), the sandbox supervisor's process and exit records, the native execution receipt itself, and the verifier pattern above rerun after execution as an operator-owned observation of filesystem effects. Choosing among them is the separate witness design.

## Acceptance and validation

Offline: the real verifier script runs locally against a fake upload, covering exact delivery, overlap refusal before any sandbox, size and type bounds, pre-existing root, corrupted, extra, symlinked, re-moded and hard-linked entries, upload failure without replay, unconfirmed discard and release, failed create, the CLI argv, pin and unknown-delivery receipts, and the real runner composed over the adapter with the reviewed SPEC-0018 bytes for both variants.

Live (`make qualify-test-workspace` on a fresh admitted kind node): for the vulnerable and fixed SPEC-0018 source, each captured by `GitSource`, two fresh sandboxes each through the real lifecycle, CLI upload, verifier and runner. Required: exact discovery of the two node ids, control passed, security failed at the reviewed assertion for vulnerable and passed for fixed, stored JUnit equal to the receipt, confirmed native deletion and no remaining Sandbox resource or boundary pod. This qualifies fixture delivery and execution only; model-authored patches, real repositories and dispositions remain unqualified.

## Decisions and open questions

The fixed upload recipe is used because the coordinator brief and ISSUE-0006 keep the general fetch blocked; it is not a general transfer contract. Source and patch share one admission so the runner sees one exact tree. Open: replacing delivery with the SPEC-0025 fetch once storage qualifies; whether release should rerun the verifier to record post-execution changes as evidence; JUnit and captured output remain workload claims. The plan is [PLAN-0032](../plans/PLAN-0032-openshell-test-workspace.md).
