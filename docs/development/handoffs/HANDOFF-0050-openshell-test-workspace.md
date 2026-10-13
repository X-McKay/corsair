---
id: HANDOFF-0050
kind: handoff
title: OpenShell test workspace adapter
status: recorded
updated: 2026-10-12
related: [SPEC-0032, PLAN-0032, SPEC-0028, SPEC-0025, ISSUE-0006]
---

# OpenShell test workspace adapter

## Verified state

Branch `claude/openshell-test-workspace-2d8497` from main `102fbef`, draft PR #31. Adds `adapters/openshell_workspace.py` (`OpenShellTestWorkspace`, `CliUpload`, fixed verifier, `WorkspaceConfig`), the runner wrapper's absolute `/bin/sh`, 19 offline checks, the live gate `make qualify-test-workspace`, [SPEC-0032](../specs/SPEC-0032-openshell-test-workspace.md), [PLAN-0032](../plans/PLAN-0032-openshell-test-workspace.md) and the [qualification report](../../qualification/openshell-test-workspace.md). Not connected to the authoring agent or the fixture chain.

## Validation and blockers

`make test-config` 766 passed in the cloud container and on RIG0, then 771 after the Codex review fixes (staging retained on upload timeout; receipt storage failures attributed to upload), which postdate the live run. Live on one fresh RIG0 kind node at `aca85a4`: the reviewed SPEC-0018 pair ran in four fresh sandboxes with exact discovery, the expected vulnerable/fixed outcomes, confirmed cleanup and no remaining cluster resources; the cluster was torn down. Unrun: a second fresh node, model-authored patches, real repositories. General source delivery stays blocked on the SPEC-0025 storage quota volume and the 0.1.3 credential placeholder check (ISSUE-0006). No witness exists; candidate telemetry is listed in SPEC-0032.

## Decisions and next steps

Delivery reuses the qualified CLI upload plus host-compared in-sandbox inventory, bounded to 64 entries and 4 MiB. Next: the fixture end-to-end chain wires this adapter in place of the local stand-in; later swap delivery for the SPEC-0025 fetch once storage qualifies. Merge only on Al's instruction.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then SPEC-0032, PLAN-0032, the openshell-test-workspace qualification report and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. Wire OpenShellTestWorkspace into the fixture end-to-end chain or requalify it on a second fresh node. Stop real-repository use while SPEC-0025 storage and credential gates remain blocked. Run make test-config and the affected live gate, preserve evidence, update records/CURRENT.md, and write a new handoff.
```
