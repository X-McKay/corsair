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

Branch `claude/benchmark-readiness-7xbmvr` from main `334aa03`, draft PR #39. Delivered offline: SPEC-0036 (XFS project quota for `/sandbox` via the 0.1.3 chart's `workspaceStorageClass`, `/tmp` removed from the workspace policy, namespace quota, `LimitRange` backstop, admission guard), its manifests under `deploy/storage/`, `deploy/openshell/values-workspace-quota.yaml`, `policies/openshell/workspace.yaml`, `make workspace-storage`, and the plain-pod storage-stage gate `make qualify-workspace-quota` (`tests/qualification/test_workspace_quota.py`, unrun); IDEA-0005 gap inventory over all 50 candidate cases; IDEA-0005 step 1 (`benchmarks/cases/jspwiki-forwarding/case.yaml`, `evals/benchmark/`); G15 (automatic toolchain, runtime and framework resolution from each case's build files, per the owner's 2026-10-13 direction) added to the inventory, loader and order; `.worktrees/` ignored for in-repo RIG0 worktrees. Nothing applied to a cluster, connected to the chain or qualified. Default gateway values, the identity policy and the SPEC-0032 workspace are unchanged.

## Validation and blockers

- `make test-config`: 888 passed (853 on main; 14 quota guards including the setup/teardown scripts under shims; 21 benchmark case checks). PR CI offline-guards green on `f8d28c3`.
- RIG0 probe (Remote Control, no cluster use, evidence `.runs/storage-probe-20261013T042732Z/` on RIG0): the XFS format step was refused by the owner's local Bash hook (`mkfs`), so byte and inode enforcement is unconfirmed. The pinned node image lacks `xfs_quota`; the pinned provisioner build lists no `--allow-unsafe-helper-pod-template`. Cleanup confirmed.
- Cluster handover attempt (05:12Z): the RIG0 session's auto-mode check refused the worktree (`Modify Shared Resources`) and every kubectl/docker call on `kind-corsair` (`Interfere With Workloads`); nothing ran. The kind cluster is again held by the witness thread for its live chain.
- Unrun: `make workspace-storage` (bootstrap, helper image and the provisioner's acceptance of the privileged helper template), the plain-pod storage gate (real byte/inode enforcement and containment; the shimmed script tests do not settle it), the still-unwritten OpenShell-stage gate (workspace policy `/tmp` denial, gateway overlay, admission guard and `LimitRange` on real sandboxes), and the SPEC-0032/E2E-0 rerun on the quota class.
- Owner review of `ff61909` (2026-10-13): 888 offline checks reproduced, CI green, no code defect found; draft scope kept.

## Decisions and next steps

The owner either runs the posted commands from `/home/al/git/corsair/.worktrees/pr39` or adds allow rules for `git worktree add`, `make workspace-storage` and `make qualify-workspace-quota` (the bootstrap formats an image with `mkfs.xfs`, which his hook otherwise refuses). Then, once the witness thread hands the cluster back: `make workspace-storage` and `make qualify-workspace-quota` on a fresh node (twice, per SPEC-0036), pin the helper's package versions from the build receipt, then write and run the OpenShell-stage gate. Independent offline follow-ups from IDEA-0005: host acquisition (step 2), repository-scale source access (step 3), Java test identity and Surefire parsing (step 5).

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then SPEC-0036, PLAN-0040, IDEA-0005 and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. Once the owner has run or allowed the posted commands and the kind cluster is handed over, run make workspace-storage and make qualify-workspace-quota from /home/al/git/corsair/.worktrees/pr39 on a fresh node, recording byte/inode refusal, containment and cleanup in PLAN-0040; then write the OpenShell-stage gate (/tmp denial, gateway overlay, admission guard). Do not claim storage enforcement or unblock SPEC-0025 until that gate passes; continue IDEA-0005 offline steps meanwhile. Run make test-config, preserve evidence under .runs/, update PLAN-0040/CURRENT.md and write a new handoff.
```
