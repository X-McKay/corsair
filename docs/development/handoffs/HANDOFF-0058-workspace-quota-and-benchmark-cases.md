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

**Update 2026-10-13 09:20Z: quota deferred.** The owner chose to defer the SPEC-0036 quota as hardening after the live gate stayed blocked (auto-mode refusals, and his Bash hook refusing `mkfs.`, `dd if=` and `kubectl delete namespace`, which the gate uses). In its place, SPEC-0025 now admits public benchmark runs with one sandbox per node behind a pre-flight `WorkspaceBudget` (`nodes/source_fetch.py`, unit-tested, not yet called by any route): tree at most a quarter of the workspace, node free space at least workspace plus reserve, quota recorded unqualified. G1 no longer blocks benchmark cases; G15 runtime selection is next on the critical path (its own thread). A tmpfs-per-volume probe on RIG0 enforced bytes and inodes synchronously and is the simpler route when the quota returns (SPEC-0036). The XFS manifests and gates stay in the branch, unrun.

Next: (JSPWiki issue text reviewed 2026-10-13, see PLAN-0040.) Connect `admit_workspace_budget` when the SPEC-0025 fetch route is wired (G3), with the operator's workspace size and reserve in configuration. Independent offline follow-ups from IDEA-0005 continue in their own threads.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then SPEC-0036, PLAN-0040, IDEA-0005 and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. The SPEC-0036 quota is deferred (owner, 2026-10-13): do not run its gates unless the owner revives it; if so, prefer the tmpfs-per-volume route recorded in SPEC-0036. Live fetch uses SPEC-0025's pre-flight WorkspaceBudget and records storage enforcement as unqualified. Never claim a storage bound during a run. Run make test-config, preserve evidence under .runs/, update PLAN-0040/CURRENT.md and write a new handoff.
```
