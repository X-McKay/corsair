---
id: SPEC-0036
kind: spec
title: Sandbox workspace storage quota
status: draft
updated: 2026-10-13
related: [SPEC-0025, SPEC-0026, SPEC-0006, SPEC-0032, PLAN-0034, PLAN-0040, ISSUE-0006, IDEA-0005]
---

# Sandbox workspace storage quota

## Goal and scope

Real repositories cannot run in a sandbox until their bytes and inodes are bounded. [SPEC-0025](SPEC-0025-sandbox-source-fetch.md) blocks live in-sandbox fetch on "a quota-enforcing volume or an equivalent", with negative cases that write past a byte limit and past an inode limit and observe in-sandbox `ENOSPC`/`EDQUOT`, unaffected node storage and other workloads, and attribution as `sandbox` layer. [PLAN-0034](../plans/PLAN-0034-fixture-e2e-sandbox-runner.md) established on RIG0 that nothing enforces either today: the workspace claim uses kind's `standard` class (`rancher.io/local-path`, a hostPath directory), the node `/var` is ext4 without quota options, the test workspace lives in `/tmp` on the container's root overlay, and the agent container has no `ephemeral-storage` limit.

This spec selects one enforcement route reachable through the pinned OpenShell 0.1.3 gateway, names the writable paths it must cover, and defines its qualification. In scope: every path a sandbox workload can write, on the local kind tuple. Excluded: production storage classes (named only as the port's other implementations), per-case workspace sizing, network and memory limits (already enforced), and transfer criteria of ISSUE-0006.

## Boundaries and design

### What a workload can write today

Read from the pinned 0.1.3 source (`NVIDIA/OpenShell` at `e1f3c82`, `crates/openshell-driver-kubernetes/src/driver.rs`) and the policy in `policies/openshell/identity.yaml`:

| Path | Backing | Bounded by |
| --- | --- | --- |
| `/sandbox` (workdir, `include_workdir: true`) | `workspace` PVC from the gateway's `volumeClaimTemplates`, `ReadWriteOnce`, size `workspace_default_storage_size` (2Gi default), class `workspace_storage_class` | Nothing with `local-path` |
| `/tmp` (Landlock `read_write`) | container root overlay on node `/var` | Nothing (no `ephemeral-storage` limit) |
| runtime, state, proxy CA mounts | `emptyDir` medium `Memory`, no `sizeLimit` | Pod memory limit (OOM, not `ENOSPC`); not in Landlock `read_write` |
| `/dev/null` | device | n/a |

Landlock is a hard requirement in every Corsair policy and was qualified for writes outside `read_write` under [SPEC-0006](SPEC-0006-openshell-policy.md). So the workload's byte and inode use is exactly `/sandbox` plus `/tmp`.

### Gateway hooks that exist in 0.1.3

- **Workspace class and size are operator chart settings.** `server.workspaceStorageClass` and `server.workspaceDefaultStorageSize` become `workspace_storage_class`/`workspace_default_storage_size`, written into each sandbox's `volumeClaimTemplates` (`default_workspace_volume_claim_templates`). Corsair already sets the class (`deploy/openshell/values.yaml`). No driver config is needed to put `/sandbox` on any storage class.
- **Driver config** (`drivers.kubernetes.allowDriverConfig`, off) adds only pre-existing PVC volumes and agent `resources` maps, with operator approval labels. It cannot add an `emptyDir`, so the PLAN-0034 memory-backed `sizeLimit` result is not reachable through it. It could carry an `ephemeral-storage` limit or a per-case pre-created claim; neither is needed for the route below.
- **The gateway builds the pod.** Init containers, extra volumes and security context are not caller-controlled, so an init-container size check is not available.

### Candidates evaluated

| Candidate | Bytes | Inodes | Synchronous in-sandbox error | Reachable in 0.1.3 | Verdict |
| --- | --- | --- | --- | --- | --- |
| Current `local-path` class with a 2Gi request | No | No | No | Yes | Rejected (PLAN-0034) |
| Storage class whose volumes enforce capacity, selected by `workspaceStorageClass` | Yes | Yes, if the volume has its own inode limit | Yes (`ENOSPC`/`EDQUOT`) | Yes | **Selected** for `/sandbox` |
| Namespace `ResourceQuota` on `requests.storage` / per-class storage | No (declared requests only) | No | No | Yes | Kept as an overcommit guard, not enforcement |
| Pod `ephemeral-storage` limits (via namespace `LimitRange` defaults or driver config) | After the fact, by kubelet eviction | No | No | Yes (`LimitRange` needs no gateway change) | Backstop for the root overlay only |
| Memory `emptyDir` with `sizeLimit` | Yes | Only via memory cgroup (OOM) | Bytes only | No (no caller volumes) | Rejected for 0.1.3 |
| Init-container size check | No (a pre-check, not a bound) | No | No | No | Rejected; the host capture gives the same pre-check (below) |
| Admission rule (native `ValidatingAdmissionPolicy`) | No | No | No | Yes | Kept as a fail-closed guard that the gateway cannot create an unbounded workspace |

### Selected route

1. **`/sandbox` on a capacity-enforcing class.** A new class `corsair-workspace` is served by a second instance of the provisioner kind already ships (pinned `kindest/local-path-provisioner` image, its own provisioner name, ConfigMap and node path, so `standard` is unchanged). Its operator-owned `setup` script, following the provisioner's upstream `examples/quota`, places each volume directory in its own XFS project on a dedicated XFS filesystem mounted with `prjquota`, and sets hard project limits for both blocks (`bhard` = the requested size, `VOL_SIZE_BYTES`) and inodes (`ihard`, a fixed operator ratio of the requested size). Unlike the upstream example, the script fails closed: if the node path is not XFS with project quota enforcement on, or either limit cannot be read back, the volume is not created and the sandbox never becomes ready (a `sandbox`-layer admission failure, not a silent unbounded volume). `teardown` clears the limits and removes the directory; confirmed cleanup checks both the PV and the project entry. The setup script also writes the effective limits into a small read-only marker the workload cannot change (the project limits themselves; `statfs` on a project-quota directory reports them, which the receipt reads).
2. **Backing filesystem bounded on the node.** The XFS filesystem is a preallocated (`fallocate`, not sparse) image file loop-mounted inside the kind node by `make`-driven bootstrap. Its size is the hard ceiling on all sandbox workspaces, independent of RIG0's own disk. A per-class `ResourceQuota` (`corsair-workspace.storageclass.storage.k8s.io/requests.storage`) in the sandbox namespace keeps the sum of requests at or below that size, so no project limit can be overcommitted and one sandbox's exhaustion cannot take bytes or inodes another sandbox was promised.
3. **No other writable byte store.** A workspace policy (new operator-owned `policies/openshell/workspace.yaml`) is the identity policy without `/tmp` in `read_write`; `/sandbox` stays writable through `include_workdir`. The operator-owned test commands set `TMPDIR` (and, for later toolchains, `java.io.tmpdir`/`MAVEN_OPTS`, `PIP_CACHE_DIR`, `HOME`) under `/sandbox`. A write to `/tmp` then fails with Landlock `EACCES`, attributed as `policy` layer. Filesystem paths are static in 0.1.3 (`include_workdir` and paths cannot change on a live sandbox), so this is fixed at creation.
4. **Root overlay backstop.** A namespace `LimitRange` gives every container in the sandbox namespace a default `ephemeral-storage` limit, so logs and anything the supervisor writes to the writable layer are bounded by eviction. This is attributed as `sandbox` layer with the eviction reason preserved. It is not counted as the synchronous bound.
5. **Fail-closed admission guard.** A native `ValidatingAdmissionPolicy` bound to the sandbox namespace refuses any `PersistentVolumeClaim` whose class is not `corsair-workspace` or whose request exceeds the operator maximum, and any `Pod` lacking an `ephemeral-storage` limit after `LimitRange` defaulting. A gateway installed with the wrong class therefore cannot start a sandbox.
6. **Sizing from the host capture.** Before creating a sandbox for a real repository, the host compares the capture's file count and byte total (SPEC-0012 snapshot) plus an operator headroom factor against the workspace limits and refuses up front as `sandbox` layer `workspace_budget` when it cannot fit. This is a deterministic pre-check, not enforcement.
7. **Attribution.** After any refused or failed run the fixed post-run receipt includes `statfs` block and inode totals and free counts for `/sandbox`. A failed command with the workspace at its block or inode limit, or an `ENOSPC`/`EDQUOT` in its retained detail, is a `sandbox`-layer `storage_exhausted` failure and can never support an application result under the SPEC-0027 gates (which already block on `sandbox`).

The workspace size is gateway-wide in 0.1.3 (`workspaceDefaultStorageSize`). The first value is 8Gi with an inode ceiling of one inode per 16 KiB (524,288), sized for the largest admitted candidate trees with build output; the backing image holds two concurrent workspaces plus 10%. Per-case sizing needs either driver-config pre-created claims or a later gateway option and is deferred until a case needs it.

### Production clusters

The storage class is the port. Block-backed CSI classes (cloud disks, Ceph RBD, TopoLVM/LVM) give each volume its own filesystem and inode table, so they meet the same contract without project quotas; the qualification below is what admits any of them. The local XFS project-quota class is the kind implementation, not a product dependency.

### Alternatives kept in reserve

- **Per-volume loop filesystem** (the setup script creates a preallocated image per volume, formats ext4 with an explicit inode count and loop-mounts it at the volume path). Same contract with stronger isolation, but one loop device per sandbox and mount propagation from a helper pod. Used if XFS project quota is unavailable on the RIG0 kernel.
- **TopoLVM or OpenEBS LVM LocalPV** on a loop-backed volume group. A new component with its own controller and scheduler extender; only if both script routes fail.

## Acceptance and validation

Offline checks: the setup script refuses non-XFS paths, missing `prjquota` and unreadable limits, and sets both `bhard` and `ihard`; class, provisioner name, quota and admission policy names agree across manifests; the per-class `ResourceQuota` does not exceed the backing image size; the workspace policy has no `/tmp` and no other `read_write` path beyond `/dev/null`; the gateway overlay sets exactly the quota class and size; operator commands place temporary and cache paths under `/sandbox`; receipt parsing maps `statfs` at limit and `ENOSPC`/`EDQUOT` detail to `sandbox`/`storage_exhausted`, and the host pre-check refuses an oversize capture.

Live qualification, on two fresh admitted RIG0 nodes with the quota class installed and the gateway on the overlay, each through a real OpenShell sandbox with confirmed cleanup:

- Byte limit: a non-root workload writing past the workspace size fails at the limit with in-sandbox `EDQUOT` or `ENOSPC` at write time; the file stops at the limit.
- Inode limit: creating files past the inode ceiling fails with the same errors before the byte limit is reached.
- Containment: during each exhaustion a second running sandbox writes and creates files normally, node `/var` free space does not change by more than the provisioner's own overhead, and the backing image size is unchanged.
- `/tmp` and other paths: a write to `/tmp`, `/dev/shm` and the home directory is denied (`EACCES`, Landlock), with the workspace untouched.
- Admission guard: a claim on `standard` or above the maximum is refused at the API; with the guard removed in a control run, the same request is accepted (so the refusal is the guard's).
- Fail-closed setup: with the node path on a non-quota filesystem in a control run, the sandbox never becomes ready and the provisioner records the script's refusal.
- Root overlay backstop: a privileged-free writer cannot reach the writable layer (Landlock) and the default limit is visible on the pod; an eviction case is not required.
- Telemetry: bytes and inodes used at refusal, time to refusal, and cleanup time recorded; missing values are unknown, not zero.

The existing SPEC-0032 fixture test workspace and the E2E-0 gate are then rerun once on the quota class with the workspace policy, to show the reviewed pair is unaffected.

## Decisions and open questions

**Deferred (owner, 2026-10-13 09:15Z).** A per-workspace quota is hardening, not a precondition for running the public benchmark cases. Until it is qualified, live runs use the SPEC-0025 pre-flight budget instead: a captured tree larger than a quarter of the configured workspace is refused (`sandbox` layer), the node must still have a full workspace plus an operator reserve free before a sandbox is created (`host` layer), and existing execution time limits apply. That bounds neither bytes nor inodes during a run, so receipts and reports record the workspace quota as unqualified; one sandbox runs at a time. The quota is required again before concurrent sandboxes on one node or workloads treated as hostile. When it is picked up, a size- and inode-limited tmpfs mounted per volume by the same provisioner `setup` script is the simpler candidate: it needs no filesystem format, quota tools or backing image. A RIG0 Docker probe (2026-10-13, `--tmpfs size=64m,nr_inodes=1000`, uid 10001, no privileges; evidence `.runs/tmpfs-probe-20261013T091539Z/` on RIG0) stopped a write at exactly 64 MiB and file creation at the inode limit with `No space left on device`, left a second mount unaffected, and charged the data to the container's memory cgroup, so the sandbox memory limit must exceed the workspace size. Kubernetes `emptyDir` cannot be used because the 0.1.3 driver admits no extra volumes. The XFS route below stays as recorded, unrun.

Selected route: XFS project quota through a second instance of the already-pinned local-path provisioner, chosen because it uses a supported gateway setting, the provisioner kind already ships and its upstream quota example, and gives both byte and inode limits with a synchronous in-sandbox error. Removing `/tmp` from the workspace policy changes the SPEC-0032 test workspace location, which was qualified under `/tmp`; it is requalified rather than assumed. Open facts, owned by [PLAN-0040](../plans/PLAN-0040-workspace-storage-quota.md): whether the RIG0 kernel and a privileged container can loop-mount XFS with `prjquota` and enforce `ihard` for a non-root writer; whether the pinned provisioner build requires `--allow-unsafe-helper-pod-template` for a privileged helper; whether `statfs` inside the sandbox reports the project limits; whether the OpenShell supervisor writes anything under `/tmp` that the workspace policy would break. For single-sandbox public benchmark runs, SPEC-0025's storage blocker is now replaced by its pre-flight `WorkspaceBudget` (deferral above), with storage enforcement recorded as unqualified; concurrent sandboxes or hostile workloads still need the live qualification above.
