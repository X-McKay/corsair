# Initial platform qualification record

Date: 2026-10-11. Outcome: **qualified for the bounded single-node ordinary-pod kind/Calico boundary on the recorded host tuple after two clean runs with confirmed cleanup**.

The bootstrap, trusted ordinary-pod fixtures, and independent ingress/egress tests are implemented and live-qualified. This result does not qualify OpenShell, Agent Sandbox, storage, gateway identity, production tenancy or benchmark workloads. No benchmark candidate is promoted by this work.

## Qualified tuple

| Component | Selection/observation |
| --- | --- |
| Host capacity | Ubuntu 24.04.5 LTS; Linux amd64; 32 CPUs; 59 GiB RAM; 589 GiB free storage |
| Kernel/runtime hints | Kernel `6.14.0-37-generic`; real `/dev/kmsg`; cgroup v2; `landlock` in the visible LSM list |
| Docker | Engine `29.8.2`; `overlay2`; local `/var/run/docker.sock` |
| Python | Host `python3.12` reported 3.12.4; uv selected CPython 3.12.13 for the project |
| uv / pytest / PyYAML | uv 0.11.12 observed; pytest 9.0.2 and PyYAML 6.0.3 locked |
| kind / Kubernetes / kubectl | v0.33.0 / v1.35.8 / v1.35.8 selected; tool checksums verified |
| Node runtime | Debian 13 kind node; kernel `6.14.0-37-generic`; containerd 2.3.4 |
| Calico | v3.33.0 official manifest checksum verified; all deployed images digest-pinned |
| Fixtures | HashiCorp http-echo 1.0.0 and curlimages/curl 8.14.1 selected by immutable digest |
| Topology | One local control-plane node; no multi-node claim |
| OpenShell / Agent Sandbox | Not selected/installed/admitted during this ordinary-pod qualification; later bounded admission is recorded [separately](openshell-admission.md) |

Exact tool URLs, SHA-256 checksums and OCI digests live in [runtime-lock.yaml](../../deploy/runtime-lock.yaml). The capacity and kernel hints above are observations, not evidence that later OpenShell Landlock/seccomp/task-memory checks will pass.

## Completed checks

- Ten offline pytest checks pass: local/CNI configuration, immutable pins, workload identity/host-access restrictions, scoped network rules, unknown timeout receipt preservation, replacement-namespace cleanup refusal, and development workflow/record guards.
- Checksum-verified kind and kubectl native version commands pass. Native kubectl Kustomize rendering uses the pinned Calico and fixture image digests.
- Two clusters were created only after native kind and Docker inspection reported no existing `corsair` cluster or control-plane container. Their Kubernetes node UIDs differ.
- On each cluster, the pinned Kubernetes version/architecture, Ready node, Ready Calico daemonset/controller and deployed Calico image digests passed the platform check.
- On each cluster, ingress and egress checks exercised direct PodIP and Service ClusterIP paths with GET and POST. Every permitted control reached the server and appeared in its logs. Each denied route/method completed three fresh curl trials with exit 28/status 000, and denied markers were absent from covered server logs. Policy removal or narrow additive allow restored reachability.
- Run 1 passed three tests in 156.07 seconds; run 2 passed three tests in 155.98 seconds. There were no failures, errors or skips.
- All four fixture namespaces were deleted only after UID comparison; every cleanup receipt says `confirmed: true`, and live post-run inventories contained no `corsair-net-*` namespace.
- Both clusters were deleted only after container-ID comparison. Native Docker inspection confirmed the owned node absent before local owner/kubeconfig state was removed; both cleanup receipts say `confirmed: true`.

This establishes the bounded single-node ordinary-pod NetworkPolicy calibration described by [SPEC-0001](../development/specs/SPEC-0001-local-platform-qualification.md). It is not a general proof of network isolation or sandbox escape resistance.

## Retained image-delivery failure and correction

The first cluster created on this host reached the Kubernetes API and applied Calico, but `calico-node` remained in `Init:CreateContainerError`. The bootstrap had passed digest-only external references to `kind load docker-image`. The resulting containerd metadata included synthetic `docker.io/library/import-2026-10-11@...` repo digests. Kubelet's checkpoint-image check selected one of those names and failed because containerd could not resolve it:

```text
failed to check if this is a checkpoint image: failed to get image from containerd
... image "docker.io/library/import-2026-10-11@sha256:...": not found
```

The underlying Calico content and original pinned repo digest were present. This matches upstream kind issue [#4184](https://github.com/kubernetes-sigs/kind/issues/4184), which records the same synthetic archive name and checkpoint-image failure. The owned failed cluster was deleted with confirmed identity/absence.

The bounded repository correction removes archive loading for these published digest-only images. Kubernetes now gives the node's native CRI the exact digest-pinned pod references, and containerd pulls them through its supported CRI path. No tag, mirror, registry, TLS check, policy or image digest was loosened. Both subsequent clean clusters passed without synthetic imported Calico images.

## Evidence identifiers

Raw evidence remains ignored and local. The checked-in record preserves the reviewed outcomes and identifiers:

| Attempt | Evidence | Result |
| --- | --- | --- |
| Digest-archive failure | `.runs/bootstrap/d252aa9bd03b4f22a83a971c0d0223c5/` | Calico rollout timed out after 180 seconds; scoped pod/event/CRI diagnostics retained |
| Failed-attempt cleanup | `.runs/bootstrap/c8875408e6ae4b35864e0646e35798a8/cleanup.json` | Confirmed |
| Clean run 1 bootstrap | `.runs/bootstrap/737b0d52667c4ed8b7706b88d43d4e2c/` | Ready |
| Clean run 1 qualification | `.runs/network-host-001/` | 3 passed in 156.07s; node UID `4966d7bf-eba5-44cd-9972-95ee0bf434bc`; both fixture cleanups confirmed |
| Clean run 1 cleanup | `.runs/bootstrap/f7d4716ed3474669b31825e0c488b8ff/cleanup.json` | Container ID `810856456ba9ab229fb94079f8b4371097efbbf6ef1e1485c318fbbd5cb84368`; confirmed |
| Clean run 2 bootstrap | `.runs/bootstrap/0872c5a96488407fbba2ca4d32761778/` | Ready |
| Clean run 2 qualification | `.runs/network-host-002/` | 3 passed in 155.98s; node UID `419ddd9e-0f0e-4c6f-b60e-e38db2bd420a`; both fixture cleanups confirmed |
| Clean run 2 cleanup | `.runs/bootstrap/9c97eff6b7894799afc06ab94aebe079/cleanup.json` | Container ID `a34995046b3fc32bded713d78ea59adeae2d3751ff8fd40d5a47240192bec29d`; confirmed |

Kubeconfigs, ownership state and raw private logs are not publication artifacts.

## Preserved unsupported-host history

The earlier managed environment remains unsupported: Docker 28.4.0, kernel 6.18.44 and outer `vfs` storage. Kind failed before Calico because kubelet lacked `/dev/kmsg`; diagnostic-only restoration of the real device entry exposed nested overlay mount `invalid argument` failures. No fake device, alternate snapshotter, host repair or policy weakening was retained. The owned node was deleted and its absence confirmed. Success on the qualified `overlay2` host does not retroactively qualify that environment.

## Next acceptance gate

The remaining 1A Agent Sandbox installation, local-path PVC persistence and native OpenShell kernel primitive admission have since passed on two fresh clusters with confirmed cleanup; see the [separate reviewed admission record](openshell-admission.md), [PLAN-0003](../development/plans/PLAN-0003-openshell-admission.md) and [runbook](../runbooks/openshell-admission.md). This does not broaden the ordinary-pod report's own coverage. The historical raw evidence referenced above is absent in the continuation checkout; that session verified the published revision/report and matching source, without claiming a raw-log re-audit.

The next bounded slice is 1B gateway/identity with the selected immutable artifacts, native chart preflight, verified TLS/local isolation and actual generated identities/mounts. Lifecycle, policy, toolchain and recovery follow separately in the [OpenShell milestone](../openshell-milestone.md). Application adapters, PydanticAI agents and Temporal remain later work.

## Primary sources

- [kind v0.33.0 release and node image digests](https://github.com/kubernetes-sigs/kind/releases/tag/v0.33.0).
- [kind issue #4184: synthetic import image name and checkpoint failure](https://github.com/kubernetes-sigs/kind/issues/4184).
- [Calico on kind](https://docs.tigera.io/calico/latest/getting-started/kubernetes/kind) and [selected official manifest](https://github.com/projectcalico/calico/blob/v3.33.0/manifests/calico.yaml).
- [Kubernetes NetworkPolicy semantics](https://kubernetes.io/docs/concepts/services-networking/network-policies/), including additive allows and CNI implementation requirements.
- [http-echo request logging implementation](https://github.com/hashicorp/http-echo/blob/v1.0.0/handlers.go).
