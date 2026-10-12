# Local OpenShell gateway and identity qualification

This implements only [Milestone 1B](../openshell-milestone.md). Read the [gateway report](../qualification/openshell-gateway.md), [admission runbook](openshell-admission.md) and [PLAN-0004](../development/plans/PLAN-0004-openshell-gateway-identity.md). Use the explicitly owned single-node kind cluster. No adapters, model calls, production tenancy or durable execution are admitted by this procedure.

```shell
make admission-artifacts
make test-config
make kind-up
make admission-install
make qualify-admission CORSAIR_QUAL_RUN=.runs/gateway-prerequisite-NEW
make openshell-install CORSAIR_ADMISSION_RUN=.runs/gateway-prerequisite-NEW
make qualify-gateway CORSAIR_QUAL_RUN=.runs/gateway-NEW
make kind-down
```

Choose new, nonexistent gateway evidence directories; the Make target refuses reuse before pytest can overwrite JUnit. Installation requires successful storage/kernel admission for this exact node UID and runtime lock, including admission fixture/PV cleanup. The official chart archive and CLI binary are checksum-verified. Installation refuses an existing namespace/private owner and keeps native Agent Sandbox discovery enabled. Helm install has bounded native waits and no automatic retry, rollback or resource adoption. A failed/unknown install stays inspectable under `.runs/gateway-install/` and `.state/openshell/owner.json`.

The profile uses the release's default mTLS caller authentication. TLS remains enabled, anonymous users disabled, and the supported port-forward binds explicitly to 127.0.0.1. Generated client CA/certificate/key are exported directly into private `.state/openshell/` CLI state with private file permissions. The dedicated export receipts withhold all credential output. CLI environment input is limited to PATH/locale/timezone and the explicit private XDG location; no ambient OpenShell flags, provider auth or policy overrides apply. Do not copy Secret objects, kubeconfigs, bearer tokens or environments into run evidence or Git.

The CLI's native status and sandbox list are authenticated positive controls. Curl verifies server trust and hostname, then rejects wrong trust/hostname. A native HTTP/2 POST to the protected ListSandboxes method without a client identity must return gRPC Unauthenticated (16), before request-body decoding. This is an authentication rejection probe, not a custom gRPC client. The HTTP health endpoints use the chart's separate health port; do not expect JSON from `/health` on the gRPC port.

One inert native sandbox uses the pinned Ubuntu workload, the operator-owned [identity policy](../../policies/openshell/identity.yaml), hard Landlock requirement, no outbound network grants/providers, CPU 1 and memory 512Mi. Its generated name fits the release's 19-character limit. Inspect the actual immutable Sandbox UID, supervisor/workload Pod UIDs, native runtime identity URI, accepted policy hash, effective container/pod UID/GID 10001, dropped capabilities, no privilege escalation, RuntimeDefault and no host namespaces/mounts.

Workload containers must have no Kubernetes token projection, Secret mount, secret environment source or provider attachment. The native bootstrap init alone receives the boundary Secret and stages protected runtime state in memory; it is absent from the running workload's mounts. The supervisor retains its audience-bound projected identity and CA-only client Secret projection. Never remove these native authentication requirements globally.

A pinned trusted curl Pod uses only the public gateway CA. Three rounds probe both gateway Service and Pod routes: the trusted Pod must receive the expected unauthenticated API response, while a direct operator process in the actual workload Pod must time out connecting to each same route. This observes the outer CNI fence independently of an intercepted OpenShell command. It does not qualify general application policy or escape resistance.

The test retains native command receipts/JUnit, actual metadata and control results. It compares native sandbox identity before delete, confirms gateway listing absence, compares namespace UID before Helm/namespace teardown and observes every collected PV's immutable identity and disappearance. Namespace deletion also covers native retained workspace PVCs and Helm's kept encryption-key Secret. Credentials are removed only after namespace/PV cleanup; the known port-forward child is terminated and reaped. No raw gateway/supervisor logs are automatically collected because authentication material may appear there; readiness, admission and metadata receipts cover this slice.

If installation or cleanup fails, retain its native result and inspect scoped Pods/events/PVCs without Secret payloads. Do not blindly repeat installation/create/delete, delete a same-name replacement, remove finalizers or relax policy/TLS/kernel/pins. Reconcile the owned namespace and cluster container IDs before cleanup. `make kind-down` verifies the Docker container identity and absence; private gateway state may remain intentionally after unconfirmed fixture cleanup and requires reconciliation before another install. Missing cleanup or mandatory evidence means 1B is not qualified.
