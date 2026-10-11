# OpenShell installation, storage and kernel admission

Date: 2026-10-11. Outcome: **qualified for the bounded remaining-1A prerequisite/storage/native-kernel slice on two fresh clusters, with confirmed fixture/PV/cluster cleanup**.

This report covers Agent Sandbox installation, single-node local-path PVC persistence and OpenShell's native capability-free runtime probes. The [ordinary-pod NetworkPolicy boundary](network-platform.md) remains separately qualified. Gateway installation/identity, authenticated boundary service, OpenShell application policy, toolchains, interruption recovery, production storage/tenancy, adapters and agents are unrun. No security issue or benchmark is promoted.

## Selected immutable tuple

The host remains Ubuntu 24.04.5 LTS, Linux amd64 kernel 6.14.0-37-generic, Docker 29.8.2 with overlay2 and cgroup v2. The node is the already-selected kind v0.33.0/Kubernetes v1.35.8 image with containerd 2.3.4 and Calico v3.33.0. Exact archive hashes, source revisions, OCI index/chart digests and image references are in [runtime-lock.yaml](../../deploy/runtime-lock.yaml).

| Artifact | Selection and compatibility |
| --- | --- |
| Agent Sandbox core | v1.0.6 release manifest, SHA-256 verified; controller OCI digest frozen; served API v1beta1 |
| OpenShell | v0.1.3, source e1f3c82caa3ed3b65de22889ae7ef32a774878ef; supports v1beta1 discovery and native capability-probe |
| OpenShell chart | Official helm-chart 0.1.3 OCI manifest sha256:44ec11bbf264fde0b65c804c856113a4dd322731a8b3803315724357855a434b; archive hash verified; offline render only |
| Helm | v3.22.0 archive and binary hashes verified; follows selected setup/support docs' Helm 3.x requirement; latest Helm v4.3.0 remains unadmitted |
| Gateway/supervisor/runtime | Matching v0.1.3 publisher images frozen by OCI digest; only trusted runtime used live |
| Workload | Native default nvcr.io/nvidia/base/ubuntu:24.04 resolved to immutable OCI index digest |
| Storage | kind's selected official source constant, checksum verified, with immutable kindest local-path-provisioner/helper images; standard class, WaitForFirstConsumer, Delete reclamation |

Current upstream primary release APIs were inspected before deployment changes: OpenShell v0.1.3 published 2026-10-09, Agent Sandbox v1.0.6 published 2026-10-08, latest Helm v4.3.0 and compatible Helm v3.22.0. Research observations remain ignored under .runs/admission-research/. Artifact preparation uses native Helm digest pull and rendering; no custom registry protocol or credential broker is delivered.

## Checks and supported limits

Fourteen offline guards pass, including immutable selections, no workload credentials/host access, native profile requirements, replacement-cluster refusal, uncertain command delivery and Secret-value redaction. The official chart and native custom-resource Kustomize render passed. Only offline Helm rendering disables the chart's API discovery preflight; the checked-in values preserve it. Generated offline Secret fields are redacted before persistence, and render output cannot be installed. These are configuration checks, not live qualification.

Both successful live runs establish:

- Agent Sandbox CRD Established, controller Available, v1beta1 served, selected controller image deployed; the actual controller creates a Pod owned by the observed Sandbox UID.
- PVC Bound, marker write and exact read after a distinct replacement Pod UID, preserving the original PVC UID and PV UID. Native storage reclamation removes that observed PV after fixture teardown.
- The actual generated Pod matches UID/GID/fsGroup 10001, strict supplementary groups, RuntimeDefault seccomp, no added capabilities or privilege escalation, required namespaced port sysctl, and no API token/Secret/projected/host mounts or host/shared namespaces. Runtime copy-self stages the pinned trusted binary in a memory emptyDir; the workload remains a standard OCI image.
- Native capability-probe exits zero and reports qualified=true, Landlock ABI 6 with hard allow/deny, nested seccomp notification and atomic addfd/send, nondumpable-parent/executed-same-UID-child memory access, child core limit zero, self-protection, non-TSYNC listener/socket virtualization, loopback socket confinement, DNS bind and bounded local TCP/UDP/DNS allow/deny round trips. All required fields are asserted, including zero capabilities and no_new_privileges.
- The fixture namespace UID is checked before deletion and absence confirmed; the observed PV disappears without deleting a replacement. Cluster cleanup compares the Docker container ID and confirms absence before removing private owner/kubeconfig state.

The probe uses the production Kubernetes security-context profile and native broker-to-child topology. It does not start an authenticated supervisor/workload service, consume bootstrap credentials, attach providers, or exercise gateway policy. The fixture's deny-ingress/egress NetworkPolicy remains intact. No requirement, TLS validation, policy or immutable pin was relaxed. This is not a sandbox-escape proof or a qualification of the full OpenShell runtime lifecycle.

## Evidence and failed attempts

Raw command/resource/log evidence stays ignored and local; only this reviewed summary is published.

| Attempt | Evidence | Actual result |
| --- | --- | --- |
| Initial storage SSA install | .runs/admission-install/b198bec69a954e70892617cb4aabc613/; bootstrap .runs/bootstrap/48587d66455f4fd59d1900b1482b39c8/ | Failed on storage field ownership conflicts with kind's original client-side manager; partial storage apply observed; Agent Sandbox apply not reached |
| Failure inventory/cleanup | .runs/admission-install-failure-inventory/; .runs/bootstrap/4c34e35682ee452e839d7298787d7477/cleanup.json | Native inventory retained; cluster container ID 9cc3a5589d9892aced926a6400cfd97238d3740e5c34de902c25bc443e0b4ad8 deleted and absence confirmed |
| Successful cluster 1 | Bootstrap .runs/bootstrap/6e8c01f5a5aa431680e9278036ae7166/; install .runs/admission-install/579d34f27011404bb079b83ae023be63/; .runs/admission-host-001/ | One admission test passed in 93.53s; namespace and PV cleanup confirmed |
| Successful cluster 2 | Bootstrap .runs/bootstrap/e2e33c8356994b1c8b2c1d8380149af9/; install .runs/admission-install/e8887f501148434985bbaca060ea256a/; .runs/admission-host-002/ | One admission test passed in 93.55s; namespace and PV cleanup confirmed |
| Cluster 1 cleanup | .runs/bootstrap/7f3c282f57f54b09ac1d10ae7f056934/cleanup.json | Container eb66bb8a0c58d418740a1cdf9614d462320536a39adb750f2d779c2e8736f338 deleted and absence confirmed |
| Cluster 2 cleanup | .runs/bootstrap/c12ccbce1df547baa84cfbc961dc3d69/cleanup.json | Container d140ce9233a86a383fc261d7b8a842f9e71a015db3bcc93aa141e96ec7fd7dac deleted and absence confirmed; .runs/admission-final-inventory/ found no fixture/storage/gateway leftovers |
| Affected network consumers | .runs/network-admission-regression-001/ | Three passed in 157.77s; no failures/errors/skips; both fixture cleanups confirmed |

Native Helm digest pull initially saved a digest-derived filename while artifact preparation expected a version-derived filename (.runs/artifacts/88432a7b8ce34696beb6d970366ee164/). Helm exit was zero and the actual archive matched the frozen hash; the subsequent file lookup reported checksum mismatch because the expected path was absent. The correction accepts exactly one native output in a new private cache directory and verifies its bytes; no digest changed. Final native pull/render passed at .runs/artifacts/c321f239b8f24a8eb82c754da3911158/. Earlier offline render receipts remain at .runs/artifacts/fd3c19d799f14d0ca53045b219edca86/ and .runs/artifacts/3b50a1506be34bd0a4db8cec63e7b667/, with generated Secret fields redacted.

The retained storage failure was corrected by using kind's native client-side apply path for its existing storage objects. New Agent Sandbox resources retain server-side apply. No force-conflicts, host patch or automatic retry/adoption is used. Each subsequent attempt starts on a newly owned cluster after confirmed teardown.

An interim documentation check failed because the new runbook linked to this report before the report existed (13 passed, one link-guard failure); the report was then created and the check rerun. Initial restricted Docker/DNS access failed before authorized inspection succeeded. The reviewed offline failure summaries are retained at .runs/offline-check-history.json. These are operator/offline failures, separate from application or kernel admission. The prior published two-cluster record was checked against origin/main and matching source, but its raw .runs/ directories are absent here; this session does not claim to have re-audited those historical logs.

Final cached-input integrity guards and native Kustomize output were compared offline to the admitted installation resources (.runs/admission-render-equivalence.json); selected runtime/storage/controller inputs are unchanged. The final preparation/render check passed at .runs/artifacts/56992ccf20584ceaa3440535198de93d/.

## Repetition identities

| Run | Node UID | PVC UID | PV UID | Cleanup |
| --- | --- | --- | --- | --- |
| 1 | b1485065-4ae4-473f-a9c9-ac5bfb5bd4d9 | f82e5c5f-cc0b-4b44-92f5-ee026ca0e9c6 | 3f602e09-038a-49c8-a2cc-d1aef00d2b15 | Namespace, PV and cluster confirmed |
| 2 | ba42cfa8-e5bb-4ae9-91b4-0bb8484f0bde | 91903020-1def-42ce-a0c8-42a8dbd09de2 | 9c4139e0-7f13-464e-b941-4cee0face451 | Namespace, PV and cluster confirmed |

Both runs record two distinct controller-owned Pod UIDs around storage remount. No failures, errors or skips occurred in either admission test. Local owner/kubeconfig files and the final node container are absent.

## Measurements and next gate

Each admission run retained 42 native-command receipts. The successful probe exec took 0.049s and 0.062s as observed by the operator (including kubectl delivery); these are not pure kernel CPU timings. JUnit records wall time; per-command receipts include start times, elapsed seconds, native stdout/stderr/exit and unknown completion on timeout. Native resource records retain imageIDs, limits and termination facts. Per-download timing is not uniformly observed and is unknown. No agent/model calls occur in this slice; token/retry telemetry is not applicable. Small repetition counts do not establish fleet reliability.

Both required fresh-cluster admissions and identity-checked cleanups passed. Take a separately planned 1B gateway/identity slice with native installation, discovery preflight enabled, verified TLS/local access isolation and actual generated identities/mounts. Application adapters, PydanticAI and Temporal remain later work.

## Primary sources

- [OpenShell v0.1.3 release](https://github.com/NVIDIA/OpenShell/releases/tag/v0.1.3), [setup](https://github.com/NVIDIA/OpenShell/blob/v0.1.3/docs/kubernetes/setup.mdx) and [support matrix](https://github.com/NVIDIA/OpenShell/blob/v0.1.3/docs/about/support-matrix.mdx).
- [Native capability-probe and hard Landlock checks](https://github.com/NVIDIA/OpenShell/blob/v0.1.3/crates/openshell-sandbox/src/main.rs), [Kubernetes workload security profile](https://github.com/NVIDIA/OpenShell/blob/v0.1.3/crates/openshell-driver-kubernetes/src/driver.rs) and [chart API preflight](https://github.com/NVIDIA/OpenShell/blob/v0.1.3/deploy/helm/openshell/templates/agent-sandbox-preflight.yaml).
- [Agent Sandbox v1.0.6 release](https://github.com/kubernetes-sigs/agent-sandbox/releases/tag/v1.0.6) and [native PVC example](https://github.com/kubernetes-sigs/agent-sandbox/blob/v1.0.6/examples/sandbox-ksa/sandbox.yaml).
- [kind v0.33.0 native storage source](https://github.com/kubernetes-sigs/kind/blob/v0.33.0/pkg/build/nodeimage/const_storage.go).
- [Helm v3.22.0 release](https://github.com/helm/helm/releases/tag/v3.22.0), [latest v4.3.0](https://github.com/helm/helm/releases/tag/v4.3.0), and [native OCI digest references](https://docs.helm.sh/docs/v3/topics/registries/).
