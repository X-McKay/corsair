---
id: PLAN-0040
kind: plan
title: Workspace storage quota and benchmark readiness start
status: in_progress
updated: 2026-10-13
related: [SPEC-0036, IDEA-0005, SPEC-0025, PLAN-0034, PLAN-0021]
---

# Workspace storage quota and benchmark readiness start

## Objective and dependencies

Implement [SPEC-0036](../specs/SPEC-0036-workspace-storage-quota.md) (bytes and inodes bounded for every path a sandbox workload can write) and start [IDEA-0005](../ideas/IDEA-0005-benchmark-readiness-gaps.md) step 1 (benchmark case manifests, loader and denominator report). From main `334aa03`. Live steps need the RIG0 kind cluster, which the witness gate thread holds; offline steps continue meanwhile. Unblocks SPEC-0025 live fetch only after live qualification.

## Steps

- [x] Read the pinned OpenShell 0.1.3 source for workspace storage hooks (below).
- [x] Gap inventory across all 50 candidate cases (IDEA-0005).
- [ ] RIG0 feasibility probe without the cluster: XFS `prjquota` loop filesystem, `bhard`/`ihard` for a non-root writer, node-image mount, provisioner helper safety switch.
- [x] Operator manifests: quota class, second provisioner instance, fail-closed setup/teardown, helper image, namespace `ResourceQuota`/`LimitRange`/`ValidatingAdmissionPolicy`, gateway values overlay, workspace policy; configuration tests.
- [x] Bootstrap step (`make workspace-storage`) that creates the preallocated XFS image and mounts it in the kind node (unrun).
- [x] Owner deferred the quota (2026-10-13 09:15Z); pre-flight `WorkspaceBudget` in `nodes/source_fetch.py` with unit test; SPEC-0025/0029/0036 and IDEA-0005 updated.
- [ ] (Deferred with SPEC-0036) Receipt `statfs` parsing, `storage_exhausted` attribution.
- [x] Storage-stage gate written: `make qualify-workspace-quota` (`tests/qualification/test_workspace_quota.py`, plain pods, unrun).
- [ ] (Deferred) Run it on two fresh nodes, then an OpenShell-stage gate (workspace policy, gateway overlay, `/tmp` denial, admission guard).
- [ ] (Deferred) Rerun the SPEC-0032 workspace gate and E2E-0 on the quota class with the workspace policy.
- [x] Benchmark case manifests, loader and report (IDEA-0005 step 1).
- [x] Review, CURRENT.md, handoff ([HANDOFF-0058](../handoffs/HANDOFF-0058-workspace-quota-and-benchmark-cases.md)).

## Validation and progress

**OpenShell 0.1.3 source** (`NVIDIA/OpenShell` at `e1f3c82`, the pinned `source_revision`): the Kubernetes driver writes the `workspace` claim from `workspace_default_storage_size` (default `2Gi`) and `workspace_storage_class` (`default_workspace_volume_claim_templates`, `crates/openshell-driver-kubernetes/src/driver.rs`); the chart exposes both as `server.workspaceDefaultStorageSize`/`server.workspaceStorageClass`. Driver config admits only pre-existing PVC volumes and agent `resources` maps (`KubernetesSandboxDriverConfig`), so no `emptyDir` can be added. Runtime/state/proxy-CA volumes are memory `emptyDir`s; the workdir default is `/sandbox`; `include_workdir` and filesystem paths cannot change on a live sandbox (`openshell-server/src/grpc/validation.rs`).

**Provisioner**: kind v0.33.0 ships `rancher.io/local-path` with `setup`/`teardown` scripts in `local-path-config` (`VOL_DIR`, `VOL_SIZE_BYTES`); upstream `examples/quota` sets XFS project `bhard` and skips quota silently on non-XFS paths (SPEC-0036 makes it fail closed). Upstream now validates helper pod templates unless `--allow-unsafe-helper-pod-template` is set.

**RIG0 probe** (2026-10-13, Remote Control, no cluster use, evidence `.runs/storage-probe-20261013T042732Z/` on RIG0): kernel 6.14.0-37-generic; `xfs` not listed in `/proc/filesystems` (module not loaded; autoload untested); `/dev/loop-control` present; Docker 29.8.2; 1 GiB `fallocate` image created. The XFS step did not run: the owner's local Bash hook refused the command (`Potentially dangerous command detected: mkfs`), so there is no byte or inode enforcement result yet. The pinned kind node image has util-linux 2.41.5 and no `xfs_quota`, so quota tooling must come from a helper image. The pinned kind provisioner image (built 2026-08-20) does not list `--allow-unsafe-helper-pod-template` in `start --help`; whether that build validates helper templates is unknown until a privileged template is applied. Image deleted, no loop device attached, no probe containers left.

**Offline build** (`deploy/storage/`, `deploy/openshell/values-workspace-quota.yaml`, `policies/openshell/workspace.yaml`, `make workspace-storage`): `setup.sh`/`teardown.sh` run under shimmed `stat`/`xfs_quota`/`xfs_io` in `tests/configuration/test_workspace_quota_guards.py`: limits set and read back; refusal and no volume left for non-XFS, accounting or enforcement off, a failed limit, a mismatched read-back, block mode and sizes outside 1 MiB–16 GiB; teardown clears the project. Manifests agree on class, provisioner and ConfigMap names; per-class quota (2 × 8Gi) stays below the 18G image; the workspace policy equals the identity policy minus `/tmp`. `make test-config`: 867 passed (853 on main plus 14). Nothing applied to a cluster. Open: helper package versions are recorded at build and pinned afterwards (the cloud proxy refused the Alpine index); the node mount does not survive a node restart; `openshell-sandboxes` must exist before the gateway installs with the overlay; whether the gateway's chart RBAC covers a separate sandbox namespace in 0.1.3 is untested.

**Benchmark inventory**: see IDEA-0005; every claim cites source on `334aa03`.

**Benchmark cases** (IDEA-0005 step 1, offline, not wired into the chain): `benchmarks/cases/jspwiki-forwarding/case.yaml` splits an agent part (neutral issue, scope, repository, baseline/candidate commits, language, build system) from an evaluator part (case id, CWE, fix reference, reference test digest, hypothesised per-revision outcomes, chain oracle left null because the file-open witness cannot observe a dispatcher choice, split null, admission, blocking gaps). `evals/benchmark/cases.py` joins all 50 inventory rows with manifests and refuses manifests that disagree with the inventory, reference tests whose digest differs, and issue text naming the case, CVE/GHSA ids or a dataset; `agent_input()` builds `IssueAnalysisInput` from the agent part only. `python -m evals.benchmark.report`: 50 cases, 1 manifest, 0 admitted; every case blocked by G1, G2b, G2c, G3, G4, G7, G10, G11, G12. Defaults for rows without a manifest are a per-language table; G7 applies to all because 40 rows have no CWE, G13 to none until a build is measured. The JSPWiki issue text is unreviewed (`issue_reviewed: false`). Reference test digest recomputed: `6ebf6244…b95d`, matching the README and PLAN-0021. `make test-config`: 888 passed.

**Cluster handover attempt** (2026-10-13 05:12Z, cluster released by the witness thread): the RIG0 Remote Control session's auto-mode check refused creating a `corsair-pr39` worktree (`Modify Shared Resources`) and any kubectl/docker call against `kind-corsair` from the main checkout (`Interfere With Workloads`), so nothing ran: no image built, no class applied, no kernel facts. The `kube` fixture also requires the kubeconfig under the running checkout's own `.state/kind/`, so the gates must run from the owning checkout or one where the owner staged it.

**Storage-stage gate (unrun)**: two 64Mi claims on `corsair-workspace` (inode ceiling 4,096) with non-root, read-only-root writer pods; asserts `EDQUOT`/`ENOSPC` and a file at or under 64 MiB on a 128 MiB write, empty-file creation stopped below 4,096, the second claim unaffected (8 MiB and 100 files), the backing image size unchanged and node `/var` drift under 8 MiB; cleanup confirms namespace, PVs and volume directories absent. Sizing note from the acquisition thread (PR #42): the largest fetched repository is 209 MB, so 8Gi workspaces leave room for builds.

**Deferral** (2026-10-13 09:15Z, owner answered "Yes" to deferring): the live gate stayed blocked because RIG0's auto-mode check refused the worktree and every kubectl/docker call against `kind-corsair`, and the owner's Bash hook is a substring match refusing `mkfs.`, `dd if=`, `kubectl delete namespace`, `kubectl delete --all` and `rm -rf /`, three of which the gate uses (format, byte fill, cleanup); they are not hidden behind make targets. Replacement: `WorkspaceBudget(workspace_bytes, reserve_bytes, node_path)` and `admit_workspace_budget` refuse, before a sandbox exists, a tree over a quarter of the workspace (`sandbox`) or a node with less than workspace plus reserve free (`host`); `node_free_bytes` reads `shutil.disk_usage` at the operator's node path. Not connected to a caller yet (the fetch route is unconnected). RIG0 had about 577 GB free (owner device session, 2026-10-13). tmpfs probe recorded in SPEC-0036. `tests/unit/test_source_fetch.py`: 77 passed; `make test-config`: 983 passed after merging main `edaea39`; 986 after the Codex review fixes (anchored commit fields, UID-bound gate cleanup); 993 after the owner's cleanup-reporting finding (a failed or uncertain namespace query is recorded as unknown, never as deleted; `tests/configuration/test_workspace_quota_cleanup.py`). G1 removed from the benchmark loader's default and JSPWiki blocking gaps.

**JSPWiki issue text review** (2026-10-13, after #39 merged): two Codex reviews against baseline `f140a2a4` and fix `88d89d65`. One ran read-only on RIG0 (evidence `.runs/codex-jspwiki-review-20261013T102112Z/` there) and found the effect overstated: the code shows only the forward target taken from path info (`DefaultURLConstructor.java:278-280` into `WikiServlet.java:95-99`), not that a resource is served. The other ran on GitHub (PR #39 review comment) and found that "normal wiki page endpoint" and "away from the wiki page view" disclose the security test's expected safe target. Both found no advisory, case or dataset leak, and component scope sufficient. The owner accepted the GitHub review's replacement text; `issue_reviewed` set to true. The repository-identification smoke corpus (`evals/repository_identification/cases.yaml`) carried the same draft text; it now uses the reviewed text as `repository-identification-smoke-v2`, so earlier v1 live results are not comparable; v2 is not yet measured live. Admission still needs observed runs, a split and a chain oracle (G10).

## Decisions and next action

Selected route and alternatives are in SPEC-0036. The probe's `mkfs` step needs the owner to allow it on RIG0 (or run it); until then the XFS route is unconfirmed and the per-volume ext4 alternative is equally unconfirmed (it also formats a filesystem). Next: the offline manifests and configuration tests, the benchmark case loader, then the probe and live gate once the hook allows `mkfs` and the cluster is handed over.
