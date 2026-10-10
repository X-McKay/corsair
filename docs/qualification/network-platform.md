# Initial platform qualification record

Date: 2026-10-10. Outcome: **blocked at host/container-runtime prerequisites; no live CNI or OpenShell qualification**.

The bootstrap, trusted ordinary-pod fixtures, and independent ingress/egress tests are implemented. This record distinguishes completed offline checks from a failed live attempt. No benchmark candidate is promoted to runtime-qualified by this work.

## Selected tuple

| Component | Selection/observation |
| --- | --- |
| Python | 3.12.14 observed; project requires Python 3.12 |
| uv / pytest / PyYAML | uv 0.12.23 observed; pytest 9.0.2 and PyYAML 6.0.3 locked |
| Host | Linux amd64; Docker 28.4.0, kernel 6.18.44, Docker storage driver `vfs` observed |
| kind / Kubernetes / kubectl | v0.33.0 / v1.35.8 / v1.35.8 selected; tool checksums verified |
| Calico | v3.33.0 official manifest checksum verified; images pinned; not installed in the live attempt |
| Fixtures | HashiCorp http-echo 1.0.0 and curlimages/curl 8.14.1 selected by immutable digest |
| Topology | One local control-plane node; no multi-node claim |
| OpenShell / Agent Sandbox | Not yet selected, installed or admitted |

Exact tool URLs, SHA-256 checksums and OCI digests live in [runtime-lock.yaml](../../deploy/runtime-lock.yaml). This is a selected tuple with incomplete runtime qualification, not a support declaration.

## Completed checks

- Six offline pytest checks pass: local/CNI configuration, immutable pins, workload identity/host-access restrictions, scoped network rules, unknown timeout receipt preservation, and refusal to delete a replacement namespace.
- Native kubectl Kustomize rendering succeeds: four fixture resources with three pinned container references; 38 official Calico resources with six pinned container references. The downloaded Calico manifest matches its locked SHA-256.
- kind and kubectl native version commands pass using checksum-verified binaries. The pinned kind node image is available and node creation begins.
- The live qualification command reports three prerequisite errors, zero passing live checks and zero skips. It does not turn missing bootstrap state into an apparent qualification.
- Explicit native kind cleanup succeeds and confirms the owned node container is absent. The diagnostic changes described below are discarded with that container.

## Live bootstrap failure and diagnosis

`make kind-up` fails during control-plane initialization, before CNI installation, image loading, or network fixtures. The failing native kind command takes approximately 81.6 seconds. Kubeadm's visible symptom is inability to create its admin ClusterRoleBinding; native kubelet diagnostics identify the earlier cause:

```text
failed to run Kubelet: ... open /dev/kmsg: no such file or directory
```

For diagnosis only, the real character-device entry with major/minor 1:11 was created inside the already privileged, owned kind node. It was not substituted with `/dev/null` or a synthetic log source. Kubelet then started, exposing another underlying runtime failure:

```text
failed to create containerd task: ... failed to mount rootfs component:
... fstype: overlay ... err: invalid argument
```

The nested containerd overlay filesystem cannot start Kubernetes static-pod sandboxes on this host configuration. The API server remains unavailable. Neither failure is an OpenShell policy boundary, a repository dependency error, a Java build failure, or agent behavior: those components have not run. Automatic bootstrap performs no device repair, snapshotter substitution, or policy weakening.

Local retained evidence identifiers:

- Bootstrap receipts: `.runs/bootstrap/266e792cceb448eda4a120fda17715db/`.
- Manually collected native kind logs: that directory's `native-kind-logs/corsair-control-plane/`, including kubelet/containerd journals. Full vendor diagnostic metadata is private local material, not a publication artifact.
- Blocked qualification JUnit: `.runs/network-blocked-20261010/junit.xml`; final-source prerequisite check: `.runs/network-blocked-final-20261010/junit.xml` (three errors, zero passes/skips).
- Confirmed cleanup receipt: `.runs/bootstrap/9376da560683484c95328edcfb94830b/cleanup.json`.

Evidence remains outside Git; the checked-in report preserves the result and references. Private kubeconfig/ownership state is separate from run evidence.

## Next acceptance gate

Run the existing commands on a Linux Docker host that supports the required nested kind devices, cgroups and containerd mounts. Require all three live checks to pass, confirmed fixture cleanup, then a second clean cluster creation and run. Keep every failed attempt in evidence. A supported alternate local runtime profile may be reviewed separately; it must preserve the same acceptance tests.

Then extend 1A to actual OpenShell kernel/storage admission and move into gateway/identity qualification. Select compatible upstream Agent Sandbox, OpenShell CLI/SDK/chart/runtime artifacts before that work. The remaining lifecycle, filesystem/request policy, toolchain and recovery slices are still planned in the [OpenShell milestone](../openshell-milestone.md).

## Primary sources

- [kind v0.33.0 release and node image digests](https://github.com/kubernetes-sigs/kind/releases/tag/v0.33.0).
- [Calico on kind](https://docs.tigera.io/calico/latest/getting-started/kubernetes/kind) and [selected official manifest](https://github.com/projectcalico/calico/blob/v3.33.0/manifests/calico.yaml).
- [Kubernetes NetworkPolicy semantics](https://kubernetes.io/docs/concepts/services-networking/network-policies/), including additive allows and CNI implementation requirements.
- [http-echo request logging implementation](https://github.com/hashicorp/http-echo/blob/v1.0.0/handlers.go).
