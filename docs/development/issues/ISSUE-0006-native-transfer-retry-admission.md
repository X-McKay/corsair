---
id: ISSUE-0006
kind: issue
title: Native transfer retry and resource admission
status: blocked
updated: 2026-10-11
related: [SPEC-0011, PLAN-0013]
---

# Native transfer retry and resource admission

## Observed and expected behavior

Expected application native transfer admission distinguishes unknown mutation and bounds host extraction/resources. Pinned OpenShell0.1.3 automatically re-enters complete upload/download operations on selected errors, including errors after possible mutation, and does not expose a transfer byte quota or retry-off flag. This is an upstream capability/admission gap, not an observed live application failure or policy denial.

## Reproduction and evidence

[Exact source](https://github.com/NVIDIA/OpenShell/blob/e1f3c82caa3ed3b65de22889ae7ef32a774878ef/crates/openshell-cli/src/ssh.rs): lines64–65 fix four attempts/2s delay; sandbox_sync_up_files, sandbox_sync_up and sandbox_sync_down all call retry_sandbox_sync. Lines1818–1863 show whole-operation retry and substring matches including ssh tar extract exited and failed to extract tar archive from sandbox. Native download archive.unpack precedes child status; directory extraction creates/merges directly at the selected host destination. Upload extraction detects some type changes but is explicitly nonatomic. Native source path canonicalization does not establish atomic source/destination identity or byte limits.

Installed CLI SHA256557f8e2af1d91221211bb29cc7152d975084d2a8c9ab8c549d46c4370ccf492e matches runtime lock. ssh.rs SHA25604ec7f978ec01b57c271819a4c078089e838f7df8032f61fc61cf898bedb0e87. Actual sandbox upload/download --help has no retry/resource control. Private source/help/hash audit retained in .runs/transfers-storage-resume/native-transfer-source-audit.json. Curated installed Python SDK inspected; no transfer methods. Primary releases still OpenShell0.1.3/Agent Sandbox1.0.6. Context7 main docs are discovery only; GitHub web open initially failed; the closing native GitHub contents API at the exact pinned commit returned byte-identical ssh.rs, independently verified against the cached archive source.

## Attempts and diagnosis

Read-only source/help and earlier published execution audits only; no upload/download or cluster dispatched in this session. Do not manufacture a failure by risking arbitrary extraction merely to prove a visible source capability gap. Native1C's successful transfer controls remain valid for their original scope, without unknown-delivery/fault/byte-limit admission. No supported no-retry alternative found; no speculative wrapper/SDK patch adopted.

## Resolution criteria and next action

Require a compatible immutable supported release offering no-retry/authoritative operation reconciliation and enforceable bounded transfer/extraction, or a specifically reviewed safe narrower contract supported by actual native semantics. Requalify affected runtime/transfer boundaries with fresh nodes and negative paths before resolving. Independent local immutable source/artifact store may proceed. Do not close an external issue or contact upstream without authorization.
