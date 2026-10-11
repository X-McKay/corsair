---
id: HANDOFF-0004
kind: handoff
title: Kind and Calico boundary qualified
status: recorded
updated: 2026-10-11
related: [PLAN-0001, SPEC-0001, ISSUE-0001, HANDOFF-0003]
---

# Kind and Calico boundary qualified

## Verified state

Repository branch `main`; source/base revision `4da9deb7ef01255be8782e00f145416f060f981a`. Resolve the revision that publishes this handoff with `git log -1 --format=%H -- docs/development/handoffs/HANDOFF-0004-kind-calico-qualified.md`. At handoff creation the tracked changes are the native CRI image-delivery correction, reviewed records, current-work navigation and this handoff. Ignored `.runs/`, `.state/`, caches, tools and the virtual environment are not publication artifacts.

The ordinary-pod kind/Calico prerequisite is qualified on Ubuntu 24.04.5 LTS, Linux amd64 kernel `6.14.0-37-generic`, Docker `29.8.2` with `overlay2` and cgroup v2. The host has 32 CPUs, 59 GiB RAM and 589 GiB free storage. A real `/dev/kmsg` and the `landlock` LSM were visible during preflight. Capacity and LSM presence do not qualify later OpenShell kernel behavior.

OpenShell, Agent Sandbox, Helm artifacts, storage admission, gateway and agents are not installed or qualified. The next bounded slice is the remainder of 1A: select compatible immutable artifacts, implement supported installation prerequisites, and test PVC/storage plus actual OpenShell kernel/runtime admission. Do not start gateway, application adapters, PydanticAI agents or Temporal work first.

## Validation and blockers

The latest native GitHub Actions development run on the base revision, [run 38083973589](https://github.com/X-McKay/corsair/actions/runs/38083973589), completed successfully. `UV_CACHE_DIR=.cache/uv uv sync --locked` completed after the default user cache proved read-only and restricted DNS required the authorized network path. `make tools` verified pinned kind `v0.33.0` and kubectl `v1.35.8`. `make test-config` passed all ten offline guards. Python compilation and `git diff --check` passed for the bootstrap correction.

The first cluster on this host reached Calico but failed because `kind load docker-image` archived digest-only references under a synthetic `import-2026-10-11` name. Kubelet/containerd then returned `failed to check if this is a checkpoint image` because that synthetic repo digest was not resolvable. This matches upstream kind issue [#4184](https://github.com/kubernetes-sigs/kind/issues/4184). Evidence: `.runs/bootstrap/d252aa9bd03b4f22a83a971c0d0223c5/`; cleanup: `.runs/bootstrap/c8875408e6ae4b35864e0646e35798a8/cleanup.json` (`confirmed: true`). The bounded fix removed archive loading and leaves the exact manifest digests to the node's native CRI pull path.

Two later clean clusters passed independently:

| Run | Bootstrap | Node UID | Live result | Fixture cleanup | Cluster cleanup |
| --- | --- | --- | --- | --- | --- |
| `.runs/network-host-001/` | `.runs/bootstrap/737b0d52667c4ed8b7706b88d43d4e2c/` | `4966d7bf-eba5-44cd-9972-95ee0bf434bc` | 3 passed in 156.07s | both confirmed; no matching namespace remained | `.runs/bootstrap/f7d4716ed3474669b31825e0c488b8ff/cleanup.json`, confirmed |
| `.runs/network-host-002/` | `.runs/bootstrap/0872c5a96488407fbba2ca4d32761778/` | `419ddd9e-0f0e-4c6f-b60e-e38db2bd420a` | 3 passed in 155.98s | both confirmed; no matching namespace remained | `.runs/bootstrap/9c97eff6b7894799afc06ab94aebe079/cleanup.json`, confirmed |

Both final node containers and local ownership/kubeconfig state were confirmed absent. Raw evidence is ignored and local; the reviewed [platform qualification report](../../qualification/network-platform.md) is the publication record. The original `vfs`/missing-device host failure remains unsupported history rather than being overwritten by this host's pass.

## Decisions and next steps

Use native CRI pulls for externally published digest-pinned images; do not reintroduce digest-only Docker archive loading unless an admitted kind release fixes and qualifies that path. No registry, TLS, CNI policy, kernel requirement or image pin was weakened. [PLAN-0001](../plans/PLAN-0001-local-platform-qualification.md) is complete and [ISSUE-0001](../issues/ISSUE-0001-nested-container-runtime.md) is resolved only for the reviewed ordinary-pod boundary.

Next, recheck the selected OpenShell release against upstream primary sources, choose mutually compatible immutable Agent Sandbox, OpenShell, Helm and workload artifacts, and create/update a bounded implementation plan before changing deployment code. Exercise supported storage/PVC behavior and the production-topology kernel probes for Landlock, seccomp notification/addfd, task-memory access and listener mode. A failed mandatory admission check blocks gateway and adapter work; record the actual layer and continue independent research or offline checks.

## Continuation prompt

```text
Continue the OpenShell foundation work in X-McKay/corsair. Read AGENTS.md,
docs/development/CURRENT.md, the Corsair development/review/handoff skills,
and HANDOFF-0004-kind-calico-qualified.md. Inspect branch, git status, source
and current upstream releases before editing; verify the published two-cluster
qualification record rather than relying on the handoff alone.

The ordinary-pod kind/Calico boundary passed twice with confirmed fixture and
cluster cleanup. OpenShell and Agent Sandbox are still uninstalled and
unqualified. Take only the remaining bounded 1A installation/storage/kernel-
runtime admission slice: select compatible immutable Agent Sandbox, OpenShell,
Helm and workload artifacts from primary sources, update a focused plan, use
supported native installation and probes, and preserve attributable evidence.
Do not begin gateway, sandbox adapter, PydanticAI agent or Temporal work before
mandatory storage and kernel admission pass. Do not weaken policy, TLS, pins or
kernel requirements to obtain a pass.

Run the smallest relevant offline checks before live work, retain every failed
attempt and identity-checked cleanup, update the qualification report and work
records, review the final diff, append a new handoff, and publish only tracked
authorized changes. Never commit .runs/, .state/, credentials or raw logs.
```
