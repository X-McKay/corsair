# OpenShell prerequisite and runtime admission

This operator slice completes the remaining 1A installation/storage/kernel admission only. It stages the trusted release runtime into an ordinary OCI workload and runs the upstream native capability probe. It does not deploy a gateway, configure user authentication, attach credentials/providers, or implement a sandbox adapter.

## Selected prerequisites

Use the [qualified ordinary-pod host](../qualification/network-platform.md), Python 3.12, uv and the explicit local Docker socket. [runtime-lock.yaml](../../deploy/runtime-lock.yaml) freezes Agent Sandbox core v1.0.6, OpenShell v0.1.3, its OCI Helm chart and four images, Helm v3.22.0, and kind's native local-path provisioner/helper artifacts. Helm 4 is not admitted by this profile. Agent Sandbox v1beta1 is supported by the selected chart and driver. Extensions, cert-manager, ingress and alternate storage/runtime profiles are unnecessary here.

```shell
make tools
make admission-artifacts
make test-config
make kind-up
make admission-install
make qualify-admission CORSAIR_QUAL_RUN=.runs/admission-001
make kind-down
```

Repeat from a second clean cluster with a new evidence directory to qualify the slice. Provisioning and prerequisite installation are explicit; tests never create a cluster. On any error, inspect the retained receipts and actual resource state before another attempt. Do not retry potentially delivered installation or exec commands blindly. Confirm kind cleanup before a fresh-cluster retry.

## Preparation and installation

`make admission-artifacts` checksum-verifies native Helm and manifests. It uses native Helm pull with an immutable OCI manifest digest, verifies the downloaded archive hash, and uses native Helm to render [values.yaml](../../deploy/openshell/values.yaml). Only offline rendering disables API discovery preflight; the tracked profile keeps it enabled. Render evidence redacts generated Secret values and is unsuitable for installation. Certificates, private keys and tokens are never copied to run evidence. Helm owns registry transport and authentication; its explicit registry-config path is private .state/helm/registry.json. This public pull needs no login.

`make admission-install` checks the local Docker container ID against private ownership, the explicit localhost kubeconfig/topology, native kubectl hash and ready/pinned Calico. It pins kind's existing native local-path storage using the upstream source constant and client-side apply, matching kind's original field-management path. It never uses force-conflicts. New Agent Sandbox core resources use server-side apply, followed by CRD Established and controller rollout checks. Existing Agent Sandbox CRDs/namespaces are refused rather than adopted. Failed partial installations remain for inspection and identity-checked cluster cleanup. No OpenShell gateway objects are installed.

## Storage and kernel gate

The trusted fixture creates one unique namespace, deny-ingress/egress NetworkPolicy and native Sandbox with volumeClaimTemplates. The controller creates the workload and PVC. The test records Sandbox, Pod, PVC and PV identities, writes a random harmless marker, deletes only the observed Pod after UID comparison, waits for the controller's replacement, and verifies the same PVC/PV remount and exact marker. This admits kind's single-node local-path behavior only; it does not qualify production storage, database durability or cross-node scheduling.

The runtime image's supported copy-self init command stages the static openshell-sandbox binary into a memory emptyDir. No runtime/supervisor is baked into the workload image. Both containers inherit UID/GID 10001 with strict groups and RuntimeDefault seccomp; privileges are disabled and all capabilities dropped. The Pod has no API token, secrets, host namespaces, host mounts or shared process namespace. The required namespaced net.ipv4.ip_unprivileged_port_start=0 setting matches the native Kubernetes driver. The admission test inspects actual generated Pod settings and image references before exec.

The native capability-probe exercises hard-requirement Landlock allow/deny and ABI >=3, nested seccomp notification and atomic addfd/send, a nondumpable broker reading an executed same-UID dumpable child, non-TSYNC listener inheritance, socket virtualization/loopback confinement, self-protection, and bounded local TCP/UDP/DNS allow/deny controls. It requires every reported primitive and native exit zero. A version string or presence of an LSM cannot pass. It does not open an authenticated supervisor/workload boundary or qualify application policy.

## Evidence and cleanup

Artifact receipts are under .runs/artifacts/<id>/; installation receipts under .runs/admission-install/<id>/; live receipts, selected-lock snapshot, cluster scope, native resource facts, admission.json, cleanup.json and JUnit XML under the operator-selected run. Commands retain argv, start time, elapsed time, stdout/stderr and exit; local timeout leaves completion unknown. Downloads have checksum outcomes but no claimed per-download latency. Model calls, tokens and agent retries are not applicable to these operator checks.

Fixture cleanup snapshots scoped pods/Sandboxes/PVCs/events and bounded native controller/provisioner logs, compares the namespace UID, deletes it and confirms absence, then waits for the observed PV UID to disappear. A replacement identity is never deleted. Cluster-scoped prerequisites belong to the dedicated kind container and are removed by make kind-down only after container-ID comparison and confirmed absence. No name-wide cleanup on another cluster is supported. Preserve unconfirmed cleanup as a blocker.

Missing image, controller, storage or kernel prerequisites retain their native failure layer; no capability, seccomp, Landlock, TLS, policy or pin is weakened. See the [reviewed admission report](../qualification/openshell-admission.md) for measured results and failed attempts. Gateway/identity is the next separately bounded slice only after required 1A admission succeeds.
