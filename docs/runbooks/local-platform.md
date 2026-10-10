# Local platform qualification

This first slice tests Kubernetes NetworkPolicy using ordinary, trusted pods. It has no model calls, application adapters, OpenShell, or Temporal dependency. Its result cannot qualify OpenShell confinement or production tenancy.

## Requirements and setup

Use Linux amd64, Python 3.12, `uv`, and a local Docker daemon at `/var/run/docker.sock`. The Docker host must support privileged kind nodes, kubelet's real kernel-device prerequisites, cgroups, and nested containerd mounts. Docker Desktop/VM/containerized environments need their own qualification; a workstation kernel version alone is insufficient.

The runtime lock pins kind, kubectl, Kubernetes/node image, the official Calico manifest, and every fixture/CNI image. Tool and manifest downloads are checksum verified. Native Kustomize pins upstream image references. Docker pulls and `kind load docker-image` supply images without adding a custom image registry or disabling TLS checks. Existing proxy, CA trust, and Docker registry configuration are preserved; remote Docker context selectors are cleared deliberately because this target owns a local cluster.

```shell
make tools
make test-config
make kind-up
make qualify-network CORSAIR_QUAL_RUN=.runs/network-001
make kind-down
```

`make tools` explicitly downloads the locked native binaries. Python dependencies come from `uv.lock`; subsequent commands use `uv run --locked`. `make test-config` runs six offline checks. Native fixture and Calico rendering can also be inspected with the installed kubectl Kustomize support; rendering does not prove runtime compatibility.

`make kind-up` creates one control-plane node, disables kind's default CNI, installs Calico's official digest-verified manifest, loads pinned images, and waits for readiness. It refuses an existing `corsair` cluster, a conflicting container name, or a stale ownership receipt. A partial bootstrap stays available for inspection and explicit cleanup; it is never silently adopted or repaired.

`make qualify-network` requires the explicit owned kubeconfig/context and an empty evidence directory. It checks the local API and expected topology before any mutation. Readiness and pinned Calico images are prerequisites for fixture creation. Each network scenario owns a fresh namespace and records its UID; cleanup refuses a replacement namespace.

## What the tests establish

| Check | Evidence |
| --- | --- |
| Platform | Locked Kubernetes version/architecture, Ready node and Calico resources, pinned deployed CNI image references |
| Ingress | Both probes initially reach the server; policy keeps selected probe reachable and denies the other; removing policy restores access |
| Egress | Both probes initially reach the server; selected probe is denied; a namespace-local TCP/5678 allow restores access; removing policies restores baseline |

Both network scenarios exercise direct PodIP and Service ClusterIP paths with GET and POST. Three fresh denied trials per route/method must time out with curl's exit 28 and HTTP status 000. Generic exec, DNS, HTTP, or connection-refused errors cannot pass as a denial. Unique successful request markers prove server log coverage; denied markers must be absent. Reachable controls and policy reversal supplement that observation. This is a bounded single-node calibration, not proof of general network isolation or escape resistance.

NetworkPolicy has no ready condition. The tests record bounded convergence attempts before demanding repeated denial; restoration also permits a bounded convergence wait. Every attempt retains its native command result. No policy is expanded automatically to make a failing check pass.

## Where to look when setup fails

Bootstrap command receipts are under `.runs/bootstrap/<id>/`, with arguments, native output/exit, start time, and elapsed time. A local subprocess timeout records partial output and leaves remote completion unknown. Failed kind creation also collects scoped kubelet/containerd journals. Use the receipt for the failing command first:

| Failing operation | Investigate |
| --- | --- |
| Tool/manifest download or checksum | Selected URL, configured network/CA trust, actual bytes/digest; never disable TLS or remove the digest check |
| Docker info/pull | Local daemon, socket access, registry response/credentials/trust; this precedes workload policy |
| kind/kubeadm creation | Kubelet and containerd journals; host devices, cgroups, filesystem mounts and control-plane health |
| Calico apply | Kubernetes admission/RBAC and the official manifest; keep the selected field manager and server-side apply |
| Calico rollout/node readiness | Native pod status, events and container logs; an installed policy object does not prove enforcement |
| Fixture readiness | Image availability, pod admission/scheduling, container startup and readiness |
| Negative traffic check | Baseline/control receipts, endpoint route, exact curl result and server marker coverage |
| Cleanup | Original UID/container ID, current identity, deletion acknowledgment and post-delete absence |

Native inspection examples use explicit local state:

```shell
.tools/linux-amd64/kubectl --kubeconfig .state/kind/kubeconfig --context kind-corsair get pods -n kube-system -o wide
.tools/linux-amd64/kubectl --kubeconfig .state/kind/kubeconfig --context kind-corsair get events -n kube-system
.tools/linux-amd64/kubectl --kubeconfig .state/kind/kubeconfig --context kind-corsair logs -n kube-system daemonset/calico-node
```

An incomplete control plane may never produce a usable kubeconfig. In that case, use the retained bootstrap journals and local Docker diagnostics. Do not synthesize `/dev/kmsg` using `/dev/null`, suppress kernel admission, loosen policies, or build a stack of undocumented patches. Qualify a compatible host or review an explicit supported platform profile before continuing.

## Evidence and cleanup

Qualification receipts, runtime-lock snapshot, scope, native resource facts/logs, denial markers, per-scenario cleanup and JUnit XML are retained in the selected `.runs/` directory. `.state/kind/` contains the ownership receipt and private kubeconfig, and must not be included in evidence exports. Caches and native tools live in ignored `.cache/` and `.tools/` directories. Run/state directories use private permissions; review native logs before sharing. No Secret objects, ambient environment dumps, model credentials, or real repository workloads are collected by these checks.

`make kind-down` compares the owned node's container ID, uses native kind deletion, and confirms container absence before removing local ownership/kubeconfig state. It refuses an unknown owner or replacement container. Run it after a partial bootstrap if ownership was recorded. Evidence survives cleanup; cached images and downloads are intentionally retained. If cleanup fails, preserve state and inspect that failure before another attempt.

The current [qualification record](../qualification/network-platform.md) documents the host blocker. After this suite passes on a fresh compatible cluster and a second clean creation, proceed to selecting and qualifying Agent Sandbox and OpenShell artifacts. Actual kernel admission, gateway identity, lifecycle, policy, toolchain and recovery gates remain outstanding.
