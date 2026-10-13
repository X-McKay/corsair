---
id: HANDOFF-0058
kind: handoff
title: Workspace storage quota design and benchmark case loader
status: recorded
updated: 2026-10-13
related: [SPEC-0036, PLAN-0040, IDEA-0005, SPEC-0025, PLAN-0021]
---

# Workspace storage quota design and benchmark case loader

## Verified state

Branch `claude/benchmark-readiness-7xbmvr` from main `334aa03`, draft PR #39. Delivered offline: SPEC-0036 (XFS project quota for `/sandbox` via the 0.1.3 chart's `workspaceStorageClass`, `/tmp` removed from the workspace policy, namespace quota, `LimitRange` backstop, admission guard), its manifests under `deploy/storage/`, `deploy/openshell/values-workspace-quota.yaml`, `policies/openshell/workspace.yaml`, `make workspace-storage`; IDEA-0005 gap inventory over all 50 candidate cases; IDEA-0005 step 1 (`benchmarks/cases/jspwiki-forwarding/case.yaml`, `evals/benchmark/`). Nothing applied to a cluster, connected to the chain or qualified. Default gateway values, the identity policy and the SPEC-0032 workspace are unchanged.

## Validation and blockers

- `make test-config`: 888 passed (853 on main; 14 quota guards including the setup/teardown scripts under shims; 21 benchmark case checks). PR CI offline-guards green on `f8d28c3`.
- RIG0 probe (Remote Control, no cluster use, evidence `.runs/storage-probe-20261013T042732Z/` on RIG0): the XFS format step was refused by the owner's local Bash hook (`mkfs`), so byte and inode enforcement is unconfirmed. The pinned node image lacks `xfs_quota`; the pinned provisioner build lists no `--allow-unsafe-helper-pod-template`. Cleanup confirmed.
- Unrun: `make workspace-storage`, the SPEC-0036 live gate (not yet written), the SPEC-0032/E2E-0 rerun on the quota class. The kind cluster is held by the witness gate thread.

## Decisions and next steps

The owner decides whether to allow `mkfs` for the probe and the bootstrap step on RIG0. Then: rerun the probe; with the cluster handed over, `make workspace-storage` on a fresh node, write and run `tests/qualification/test_workspace_quota.py` (SPEC-0036 acceptance), pin the helper's package versions from the build receipt. Independent offline follow-ups from IDEA-0005: host acquisition (step 2), repository-scale source access (step 3), Java test identity and Surefire parsing (step 5).

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then SPEC-0036, PLAN-0040, IDEA-0005 and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. If the owner has allowed mkfs on RIG0, rerun the PLAN-0040 probe; once the kind cluster is handed over, run make workspace-storage on a fresh node and write the SPEC-0036 live gate, recording byte/inode refusal, containment and cleanup in PLAN-0040. Do not claim storage enforcement or unblock SPEC-0025 until that gate passes; continue IDEA-0005 offline steps meanwhile. Run make test-config, preserve evidence under .runs/, update PLAN-0040/CURRENT.md and write a new handoff.
```
