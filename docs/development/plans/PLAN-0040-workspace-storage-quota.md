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
- [ ] Receipt `statfs` parsing, `storage_exhausted` attribution and host size pre-check; unit tests.
- [ ] Live gate `make qualify-workspace-quota` on two fresh nodes (SPEC-0036 acceptance).
- [ ] Rerun the SPEC-0032 workspace gate and E2E-0 on the quota class with the workspace policy.
- [ ] Benchmark case manifests, loader and report (IDEA-0005 step 1).
- [ ] Review, CURRENT.md, handoff.

## Validation and progress

**OpenShell 0.1.3 source** (`NVIDIA/OpenShell` at `e1f3c82`, the pinned `source_revision`): the Kubernetes driver writes the `workspace` claim from `workspace_default_storage_size` (default `2Gi`) and `workspace_storage_class` (`default_workspace_volume_claim_templates`, `crates/openshell-driver-kubernetes/src/driver.rs`); the chart exposes both as `server.workspaceDefaultStorageSize`/`server.workspaceStorageClass`. Driver config admits only pre-existing PVC volumes and agent `resources` maps (`KubernetesSandboxDriverConfig`), so no `emptyDir` can be added. Runtime/state/proxy-CA volumes are memory `emptyDir`s; the workdir default is `/sandbox`; `include_workdir` and filesystem paths cannot change on a live sandbox (`openshell-server/src/grpc/validation.rs`).

**Provisioner**: kind v0.33.0 ships `rancher.io/local-path` with `setup`/`teardown` scripts in `local-path-config` (`VOL_DIR`, `VOL_SIZE_BYTES`); upstream `examples/quota` sets XFS project `bhard` and skips quota silently on non-XFS paths (SPEC-0036 makes it fail closed). Upstream now validates helper pod templates unless `--allow-unsafe-helper-pod-template` is set.

**RIG0 probe** (2026-10-13, Remote Control, no cluster use, evidence `.runs/storage-probe-20261013T042732Z/` on RIG0): kernel 6.14.0-37-generic; `xfs` not listed in `/proc/filesystems` (module not loaded; autoload untested); `/dev/loop-control` present; Docker 29.8.2; 1 GiB `fallocate` image created. The XFS step did not run: the owner's local Bash hook refused the command (`Potentially dangerous command detected: mkfs`), so there is no byte or inode enforcement result yet. The pinned kind node image has util-linux 2.41.5 and no `xfs_quota`, so quota tooling must come from a helper image. The pinned kind provisioner image (built 2026-08-20) does not list `--allow-unsafe-helper-pod-template` in `start --help`; whether that build validates helper templates is unknown until a privileged template is applied. Image deleted, no loop device attached, no probe containers left.

**Offline build** (`deploy/storage/`, `deploy/openshell/values-workspace-quota.yaml`, `policies/openshell/workspace.yaml`, `make workspace-storage`): `setup.sh`/`teardown.sh` run under shimmed `stat`/`xfs_quota`/`xfs_io` in `tests/configuration/test_workspace_quota_guards.py`: limits set and read back; refusal and no volume left for non-XFS, accounting or enforcement off, a failed limit, a mismatched read-back, block mode and sizes outside 1 MiB–16 GiB; teardown clears the project. Manifests agree on class, provisioner and ConfigMap names; per-class quota (2 × 8Gi) stays below the 18G image; the workspace policy equals the identity policy minus `/tmp`. `make test-config`: 867 passed (853 on main plus 14). Nothing applied to a cluster. Open: helper package versions are recorded at build and pinned afterwards (the cloud proxy refused the Alpine index); the node mount does not survive a node restart; `openshell-sandboxes` must exist before the gateway installs with the overlay; whether the gateway's chart RBAC covers a separate sandbox namespace in 0.1.3 is untested.

**Benchmark inventory**: see IDEA-0005; every claim cites source on `334aa03`.

## Decisions and next action

Selected route and alternatives are in SPEC-0036. The probe's `mkfs` step needs the owner to allow it on RIG0 (or run it); until then the XFS route is unconfirmed and the per-volume ext4 alternative is equally unconfirmed (it also formats a filesystem). Next: the offline manifests and configuration tests, the benchmark case loader, then the probe and live gate once the hook allows `mkfs` and the cluster is handed over.
