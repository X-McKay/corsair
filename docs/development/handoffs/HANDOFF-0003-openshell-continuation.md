---
id: HANDOFF-0003
kind: handoff
title: OpenShell continuation and host requirements
status: recorded
updated: 2026-10-10
related: [PLAN-0001, SPEC-0001, ISSUE-0001, ISSUE-0002, HANDOFF-0002]
---

# OpenShell continuation and host requirements

Use the continuation prompt at the end of this document to start a fresh session. Provision the host described below first if the current environment cannot run privileged kind nodes and their nested workloads.

## Verified state

Repository: [X-McKay/corsair](https://github.com/X-McKay/corsair), branch `main`. Source/base revision for this handoff: `e5ac94dc6d311f5d5b900aee1f7a3827cf48f4f9`. The handoff and navigation updates are published together; resolve their actual revision with `git log -1 --format=%H -- docs/development/handoffs/HANDOFF-0003-openshell-continuation.md`. Inspect current git state rather than assuming `main` still points to that revision.

The first platform subset is implemented, but **live qualification is blocked**. OpenShell, Agent Sandbox, application adapters, agents and Temporal are not installed or qualified. The immediate task is to qualify the existing ordinary-pod Kubernetes/CNI tests on a compatible host, twice from clean clusters. This is the first dependency gate within Milestone 1A, not completion of OpenShell qualification.

The broader agreed design uses Kubernetes (local kind, eventual existing-cluster namespace), PydanticAI, native Temporal durability, five focused agents, narrow ports and SDK-backed adapters. Each investigation produces exactly two native tests: a benign control and a security regression, with scoped evidence for InfoSec. Local/Bedrock models and GitHub/Azure issue sources remain planned interchangeable adapters. Do not start those components during this foundation task.

Read only the relevant sources initially:

1. [AGENTS.md](../../../AGENTS.md), [current work](../CURRENT.md), and [development guide](../README.md).
2. [PLAN-0001](../plans/PLAN-0001-local-platform-qualification.md), [SPEC-0001](../specs/SPEC-0001-local-platform-qualification.md), and [ISSUE-0001](../issues/ISSUE-0001-nested-container-runtime.md).
3. [Reviewed platform failure](../../qualification/network-platform.md) and [local platform runbook](../../runbooks/local-platform.md).
4. [OpenShell milestone](../../openshell-milestone.md) for the intended structure, dependency order and acceptance; [implementation plan](../../implementation-plan.md) for subsequent milestones.

Current implementation locations:

| Location | Responsibility |
| --- | --- |
| `deploy/runtime-lock.yaml` | Selected versions, SHA checksums and OCI image digests |
| `deploy/kind/bootstrap.py`, `cluster.yaml` | Explicit native tools/bootstrap and identity-checked cleanup |
| `deploy/qualification/` | Trusted ordinary-pod HTTP fixtures and ingress/egress policies |
| `tests/configuration/` | Ten offline configuration, evidence and workflow guards |
| `tests/qualification/` | Three live platform/network tests and bounded command receipts |
| `.runs/` | Ignored evidence; separate directories for each attempt |
| `.state/kind/` | Ignored private kubeconfig and cluster ownership receipt |
| `.claude/skills/`, `.agents/skills/` | Canonical shared skills and Codex symlink aliases |

Selected runtime tuple: Linux amd64, kind `v0.33.0`, Kubernetes/kubectl `v1.35.8`, Calico `v3.33.0`, digest-pinned node/CNI/echo/curl images. The lock file is authoritative. OpenShell `v0.1.2` is the documentation/source research reference, **not an admitted deployment pin**. Agent Sandbox, Helm, OpenShell chart/CLI/SDK and runtime images still need compatible immutable selections.

## Validation and blockers

At the base revision, ten offline guards passed locally and in a fresh checkout. Native [GitHub Actions run 38083065271](https://github.com/X-McKay/corsair/actions/runs/38083065271) passed on `e5ac94d`, including setup-uv cache cleanup. For this handoff update, `make test-config` passed all ten checks on Python 3.12.14, and `git diff --check` passed. Live qualification was not rerun for this documentation-only change. Offline CI does not exercise Docker, CNI, OpenShell or native agent-client behavior.

The previous managed environment had Docker `28.4.0`, kernel `6.18.44`, and outer Docker storage driver `vfs`. Kind failed before Calico installation. Kubelet initially lacked `/dev/kmsg`; a diagnostic-only restoration of the real kernel character-device entry inside the owned node exposed containerd's nested overlay mount failure (`invalid argument`). The kubeadm ClusterRoleBinding failure was a downstream symptom. No host repair, alternate snapshotter or workaround was retained. The owned node was deleted and its absence confirmed.

All three live tests were blocked by prerequisites; none passed. Original raw artifacts under `.runs/` are ignored and **will not exist in a fresh clone**. The checked-in qualification report records reviewed facts and artifact identifiers. Generate new evidence on the new host; do not infer qualification from unavailable old logs.

[ISSUE-0002](../issues/ISSUE-0002-native-client-discovery.md) remains open: skill layout checks pass, but native Codex discovery was blocked by read-only client state and Claude was unavailable. A new client can explicitly read the checked-in skills if discovery is unavailable. This does not qualify native discovery or block the independent platform task.

## Hardware and host requirements

### Recommended capacity for this milestone

These are planning recommendations for one kind control plane and small serial qualification workloads, **not benchmarked minimum requirements or a concurrency promise**. Capacity should be remeasured once OpenShell and toolchain fixtures run.

| Resource | Starting recommendation | Comfortable development allocation |
| --- | --- | --- |
| CPU | 4 x86_64 vCPUs | 8 x86_64 vCPUs |
| RAM | 16 GiB | 32 GiB |
| Storage | 60 GiB free SSD-backed space for Docker, checkout, caches and evidence | 100 GiB free; add capacity for retained images and Java/Maven caches |
| GPU | None required | Local model hosting is a separate later capacity decision |
| Host | Native Linux amd64 or a full Linux amd64 VM | Ubuntu 24.04 LTS with an enabled compatible kernel is a reasonable candidate, subject to actual qualification |

Use a conventional Docker host rather than another restricted development container. Containers share the host kernel: increasing RAM or choosing a newer container image will not fix missing kernel facilities or forbidden nested mounts. A full Linux VM can provide an independent kernel; this kind/Docker profile does not require the OpenShell MicroVM driver or `/dev/kvm`.

### Mandatory capabilities and software

| Boundary | Required behavior |
| --- | --- |
| Corsair bootstrap | Linux `x86_64` and a local Docker Engine/socket at `/var/run/docker.sock`; current code rejects other platforms and deliberately clears remote Docker selectors |
| Docker/kind | Operator access to create privileged kind nodes; usable cgroups and real kernel devices; containerd must start nested Kubernetes workloads on the actual backing filesystem/runtime |
| OpenShell prerequisites | Upstream v0.1.2 lists Docker Engine/Desktop 28.0+, Kubernetes 1.29+, and Helm 3.x. Keep the repository's selected Kubernetes tuple; select/pin Helm when its install slice is implemented |
| Kernel filesystem isolation | Enabled Landlock ABI 3+ (introduced in upstream Linux 6.2); distributions/backports require the same actual admission. Use `landlock.compatibility: hard_requirement` |
| Kernel syscall mediation | Nested seccomp user-notification filters and atomic `SECCOMP_IOCTL_NOTIF_ADDFD` with `SECCOMP_ADDFD_FLAG_SEND` must work under the actual runtime profile without added workload capabilities |
| Kernel memory access | Non-dumpable broker must access its same-UID dumpable workload child's memory via `process_vm_readv`/`process_vm_writev` or `/proc/<pid>/mem`; require the upstream production-topology probe |
| Listener mode | Prefer verified `killable` notification mode (`WAIT_KILLABLE_RECV`, Linux 5.19+ or backport); do not silently accept an unqualified legacy/reduced mode |
| Kubernetes isolation | Actual ingress **and** egress NetworkPolicy enforcement; RBAC, admitted storage/PVC behavior, then compatible Agent Sandbox controller/CRDs before OpenShell installation |
| Development tools | Git, Make, Docker CLI, Python 3.12 and uv; CI selects uv `0.12.23`. Python dependencies are selected by `uv.lock`; use `uv run --locked` |
| Network/trust | Working HTTPS/DNS access for selected tool, manifest, Python package and OCI image sources; preserve configured CA/proxy/registry trust. No TLS bypass |

Docker administration is effectively host-privileged and belongs to the trusted operator. Do not expose the Docker socket, operator kubeconfig or cloud/model/repository credentials to sandbox workloads. Later production namespace deployment will still need operator-supplied cluster-scoped CNI, CRDs/controller, RBAC, kernel and storage prerequisites.

Initial download sources include GitHub/releases/raw files, `dl.k8s.io`, PyPI package/index hosts, Docker Hub and Quay. The later OpenShell slice also needs its selected GHCR artifacts, Agent Sandbox registry artifacts, and the explicitly selected workload image (upstream defaults to NVCR). Derive precise allowlists or mirrors from selected manifests/lock files; package managers and OCI registries may redirect to additional download hosts. No model endpoint or provider credentials are needed for platform qualification.

Verified upstream references (v0.1.2): [support matrix](https://github.com/NVIDIA/OpenShell/blob/v0.1.2/docs/about/support-matrix.mdx) and [Kubernetes setup](https://github.com/NVIDIA/OpenShell/blob/v0.1.2/docs/kubernetes/setup.mdx). Recheck the selected release before installation. Upstream supports other platforms/runtimes; Corsair's current bootstrap admits only its Linux amd64 candidate, and even that tuple remains unqualified.

### Read-only preflight on the proposed Docker host

Run these from the Linux host/VM, not a container that sees a different filesystem or devices. Docker's reported kernel is relevant if the daemon is virtualized. These checks collect hints; **they do not replace live Kubernetes tests or OpenShell admission**.

```shell
uname -srm
getconf _NPROCESSORS_ONLN
free -h
df -h . /var/lib/docker
python3.12 --version
uv --version
git --version
make --version
docker --host=unix:///var/run/docker.sock version --format '{{.Server.Version}}'
docker --host=unix:///var/run/docker.sock info --format 'kernel={{.KernelVersion}} architecture={{.Architecture}} storage={{.Driver}} cgroup={{.CgroupVersion}} root={{.DockerRootDir}}'
ls -l /dev/kmsg
cat /sys/fs/cgroup/cgroup.controllers
cat /sys/kernel/security/lsm
```

Check free space on Docker's reported root path if it differs from `/var/lib/docker`. A missing `cgroup.controllers` can indicate cgroup v1; a missing LSM listing can indicate an unmounted security filesystem or limited visibility. Diagnose rather than declaring either fact sufficient proof of incompatibility. Landlock's presence in the LSM list does not establish its ABI or syscall usability. A missing `/dev/kmsg`, `vfs` outer storage, or containerized host deserves investigation in light of the recorded failure; the actual node/containerd outcome decides this gate. Do not create fake devices or change storage/security settings merely to obtain a pass.

## Decisions and next steps

Existing user authorization covers continued implementation and publication to Corsair. Follow the shared development, review and handoff skills. Keep work bounded, use native capabilities, preserve unrelated changes and never publish `.state/`, `.runs/`, credentials or raw private logs.

1. Clone or update the repository on the proposed host, inspect git state, read the sources above, and run the preflight. Install missing trusted host tools using their supported procedures; use the locked dependency setup below.
2. Run the first clean cluster and all three live checks. Keep every attempt's bootstrap receipts and separate network evidence directory. Use the runbook to attribute failures to download/trust, host/runtime, Kubernetes/CNI, fixture or cleanup layers.
3. Confirm fixture namespace cleanup and explicit cluster cleanup, then repeat on a second clean cluster with a new evidence directory. Require all three live tests to pass on each run and confirmed immutable-identity cleanup before resolving ISSUE-0001 or advancing.
4. Update the reviewed qualification report, PLAN-0001 and CURRENT with the actual host/runtime tuple, outcomes and evidence references. A previously failed host remains unsupported by these new-host results; retain its failure history.
5. Only after that gate passes, select compatible immutable Agent Sandbox/OpenShell/Helm artifacts and implement the next bounded 1A slice: supported installation prerequisites, storage/PVC behavior and actual OpenShell kernel/runtime admission. Follow the existing milestone plan to reach 1B gateway/identity, then lifecycle, policy, toolchains and recovery. Do not invent a broad wrapper or application orchestration yet.

On a fresh host, setup and first run:

```shell
git clone https://github.com/X-McKay/corsair.git
cd corsair
git status --short --branch
git log -1 --oneline
uv sync --locked
make tools
make test-config
make kind-up
make qualify-network CORSAIR_QUAL_RUN=.runs/network-host-001
make kind-down
```

Execute setup/run commands individually, inspecting each result before the next. If `kind-up` fails, retain diagnostics and run `kind-down` **when ownership was recorded**, even though the success path did not complete. If ownership is absent or identity changed, inspect the native state and ownership failure instead of deleting by name. If qualification fails, retain evidence and still perform ownership-checked cleanup. If cleanup is unconfirmed, resolve that before another creation. Never blindly delete an existing `corsair` cluster or its receipt to force progress.

After confirmed cleanup, repeat:

```shell
make kind-up
make qualify-network CORSAIR_QUAL_RUN=.runs/network-host-002
make kind-down
```

Use new evidence directories for retries; existing evidence is not overwritten. These are currently implemented Make targets. `openshell-install` and later lifecycle/policy/toolchain/recovery targets in the milestone document are illustrative future work, not executable features today.

## Continuation prompt

```text
Continue the OpenShell foundation work in X-McKay/corsair. Read AGENTS.md,
docs/development/CURRENT.md, and
docs/development/handoffs/HANDOFF-0003-openshell-continuation.md first.
Use the Corsair development skill; explicitly read its SKILL.md if the client
does not discover it. Inspect branch, git status, current source and native CI
before editing. Preserve unrelated changes and verify handoff claims.

Read PLAN-0001, SPEC-0001, ISSUE-0001, docs/qualification/network-platform.md,
docs/runbooks/local-platform.md and docs/openshell-milestone.md. The current
gate is the existing ordinary-pod kind/Calico qualification, not agent work.
It is implemented but blocked on the previous nested host. OpenShell and
Agent Sandbox artifacts are not yet selected/installed/admitted.

Verify this host against the handoff's hardware/capability requirements.
Recommended starting capacity: Linux amd64 host/full VM, 4 vCPUs, 16 GiB RAM,
60 GiB free SSD space; no GPU or model credentials needed. Capability probes
and live tests, not capacity or kernel version alone, determine compatibility.

Run locked setup, make test-config, make kind-up and make qualify-network
with a fresh evidence directory. Preserve each failure and native receipts;
confirm identity-checked fixture/cluster cleanup even after partial bootstrap.
Repeat from a second clean cluster with separate evidence. Require all three
live tests to pass twice with confirmed cleanup before advancing the gate.
If blocked, update the issue/plan and continue independent useful work;
do not fake devices, weaken isolation, bypass TLS, silently swap runtimes,
or integrate unqualified dependencies.

After that gate passes, document the exact qualified tuple and take only the
next bounded OpenShell 1A installation/storage/runtime-admission slice,
selecting compatible immutable upstream artifacts. Prefer native SDK/service
features and keep individual components isolated and testable. Do not start
PydanticAI agents, Temporal integration or the Sandbox adapter prematurely.
Review with corsair-review, record actual checks and unknowns, update the
living records/CURRENT, append a new handoff, and commit/push authorized work.
Keep private state, credentials and raw evidence out of Git.
```
