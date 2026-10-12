# Native readiness and lifecycle adapter probes

Use [PLAN-0010](../development/plans/PLAN-0010-native-readiness-sample.md) and [PLAN-0011](../development/plans/PLAN-0011-sandbox-lifecycle-adapter.md). Dedicated owned Linux amd64 kind node only; no ambient kubeconfig or transport fallback. Every NEW suffix must be unused. Pinned toolchain cache receipts must remain valid.

```shell
UV_OFFLINE=true make test-config
make kind-up
make admission-install
make toolchain-images-load
make qualify-admission CORSAIR_QUAL_RUN=.runs/adapter-admission-NEW
make qualify-network CORSAIR_QUAL_RUN=.runs/adapter-network-NEW
make openshell-install CORSAIR_ADMISSION_RUN=.runs/adapter-admission-NEW
make qualify-readiness CORSAIR_NETWORK_RUN=.runs/adapter-network-NEW CORSAIR_QUAL_RUN=.runs/adapter-readiness-NEW
# Each fixture removes its gateway namespace and private identity; reinstall explicitly.
make openshell-install CORSAIR_ADMISSION_RUN=.runs/adapter-admission-NEW
make qualify-adapter-lifecycle CORSAIR_NETWORK_RUN=.runs/adapter-network-NEW CORSAIR_QUAL_RUN=.runs/adapter-host-NEW
# Preserve exact-node empty resource inventory and original Docker CID before this.
make kind-down
# Confirm that original CID, owner/kubeconfig and private state are absent.
```

Audit every prerequisite's actual native receipt, node UID, runtime-lock, storage/kernel booleans and cleanup. A failed prerequisite/readiness blocks dependent workload use. Retain all attempts and source bindings; never overwrite raw directories or count successful body assertions before final fixture cleanup. Repeat on a second independently created node for adapter qualification; latency observations do not define an SLO.

The operator owns `OpenShellLifecycle(client, spec=..., workspace=..., owner=UUID(...), receipts=absolute_path)`. Client is a context-managed native SandboxClient with qualified mTLS; receipt directory exists with operator owner/mode0700 and is never mounted into the workload. `with OpenShellLifecycle(...) as lifecycle` closes only its host directory descriptor; caller closes the native client. `create(UUID)` returns an immutable handle before `wait_ready(handle, new_UUID)`; retain it for cleanup even when readiness fails. `delete(handle, new_UUID)` confirms API absence; independent original Kubernetes/storage/container observations remain required for qualification.

Never replay an unresolved intent or reuse an operation UUID. A missing result means unknown delivery. Inspect typed LifecycleError.receipt and the native chained cause, original ID and full owner labels; a receipt-storage failure can carry the acknowledged handle without a result file. Reconciliation/abandoned-resource CLI is not implemented. If no immutable ID was returned, creation remains unresolved and operator inventory/label evidence is required before any cleanup. Do not blindly delete a name with uncertain identity. Native delete is not atomic against replacement: this slice requires exclusive operator control and nonreused names, and refuses observed replacements. Preserve TLS/policy/pins/kernel requirements in all cases.
