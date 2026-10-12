---
id: SPEC-0011
kind: spec
title: Native transfer admission
status: accepted
updated: 2026-10-11
related: [PLAN-0013, ISSUE-0006]
---

# Native transfer admission

## Goal and scope

Admit only supported native upload/download with bounded resources, confined regular-file paths, expected byte/digest identity and attributable delivery over the qualified lifecycle handle. Follow [execution/recovery](../../execution-and-recovery.md); operator owns pins, policy, workspace, budgets and TLS. Do not build a transfer transport or patch upstream to bypass an admission gap.

## Boundaries and design

Pinned OpenShell0.1.3 curated Python SDK has no upload/download methods. Native CLI tar-over-SSH is the supported implementation, but its retry owner must distinguish safe reconciliation from unknown mutation. Native path/symlink preservation is broader than the first application regular-file envelope. Native installed/source bytes, not Context7 main docs, determine admission. See ISSUE-0006 for the concrete source/CLI gap.

## Acceptance and validation

Require compatible supported retry control or authoritative native operation reconciliation, host transfer byte/storage limits, regular-file/type/confinement/digest checks, original identity and protected intent/result receipts. Then smallest offline contracts followed by two fresh current-node storage/kernel/CNI/gateway-admitted matrices and original-ID cleanup. Version/help/source/render or earlier native happy-path transfers do not admit this application boundary. No app adapter/live dispatch while its prerequisite is blocked.

## Decisions and open questions

Current user continuation authorizes transfers and subsequent immutable storage; this component stays blocked rather than weakening uncertainty/resource requirements. Independent local immutable storage/source capture can proceed under its own focused spec/plan. No agents, Temporal, merges or external issue messaging.

## First native operation: trusted single-file upload

Qualify the documented CLI sandbox upload --no-git-ignore with one fixed regular host file of 1 MiB, frozen SHA256 and original local file identity, into an explicit new /tmp basename of a fresh operator-owned idle sandbox. Only trusted operator fixture bytes enter this operation; no repository code or concurrent actor runs there. Preserve existing TLS/policy/kernel/pins. Reuse existing gateway/lifecycle/cleanup fixtures, not a second transfer runtime or protocol.

The native CLI remains the retry owner (up to 4 whole-operation attempts). This narrow operation admits the final regular file only after native success, unchanged sandbox/parent identity and exact size/digest checks. A failed/lost CLI result remains unknown and is never resent by application code; the original sandbox is retired using existing identity-checked lifecycle cleanup. Repeating a native write to this isolated scratch file cannot publish an authoritative artifact or execute its bytes. This does not establish native exactly-once delivery, atomic replacement under concurrency or recovery of a failed transfer.

Two fresh admitted nodes must exercise actual successful upload, independent regular-file/digest reread and detection of a deliberately changed destination, with immutable cleanup. The 1 MiB file cap comes from the already selected source-file envelope, not a performance SLO. No untrusted host extraction occurs. Native internal retry/RPC counts remain unknown unless observed. This is native controlled-upload qualification only; the application transfer adapter, arbitrary source materialization, untrusted downloads and transport/controller loss remain unqualified. ISSUE-0006's broader gate stays blocked.
