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
