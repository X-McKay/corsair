# Native OpenShell policy qualification

Scope: only 1D on the explicitly owned single-node Linux amd64 kind environment. Read [SPEC-0006](../development/specs/SPEC-0006-openshell-policy.md), [PLAN-0007](../development/plans/PLAN-0007-openshell-policy.md) and the [milestone](../openshell-milestone.md). Toolchains, recovery, application adapters and agents have separate gates.

```sh
UV_OFFLINE=true make test-config
make tools
make admission-artifacts
make policy-image  # once: fixed Ubuntu/curl digests, no-network build, harmless canaries
make kind-up
make admission-install
make policy-image-load
make qualify-admission CORSAIR_QUAL_RUN=.runs/policy-admission-NEW
make qualify-network CORSAIR_QUAL_RUN=.runs/policy-network-NEW
for repetition in 1 2 3; do
  make openshell-install CORSAIR_ADMISSION_RUN=.runs/policy-admission-NEW || exit 1
  make qualify-policy CORSAIR_NETWORK_RUN=.runs/policy-network-NEW CORSAIR_QUAL_RUN=".runs/policy-host-NEW-$repetition" || exit 1
  # Verify policy/gateway/endpoint and original-ID cleanup receipts before proceeding.
done
make kind-down
```

Wait for each command's actual result before the next. After a failure, stop dependent work, inspect retained delivery/cleanup evidence, and perform final identity-checked cluster teardown separately. Never reuse an evidence directory or retry a possible side effect blindly. Native preparation stages the local canary image without registry publication: its Dockerfile, immutable Ubuntu and official curl artifact/config identities, native containerd manifest and content-addressed alias are retained in private local receipts. The native musl loader uses a fixed search path for the isolated curl libraries; upstream absolute libcurl symlinks are made relative in that directory. Actual executable invocation is mandatory: readlink alone cannot establish presence. Existing artifact preparation refuses silent rebuild; loading another fresh cluster must produce the same manifest. Local cached images can remain for replay; they are inert artifacts, not surviving workloads. Qualification inspects the running image identity.

Each owned node must pass actual storage/kernel and the complete ordinary-pod CNI suite with immutable fixture cleanup before gateway installation and policy work. The policy fixture checks explicit same-node CNI evidence and the gateway fixture reruns mandatory TLS/auth/identity/access-isolation controls. No ambient gateway or workload credentials, provider attachment, TLS bypass or kernel relaxation.

Two sequential static sandboxes compare canary control and restrictive filesystem policies with the same image. UID10001 can read the world-readable excluded canary and write the world-writable canary during control; restricted execution admits scratch read/write and read-only canary reads, and denies excluded read, symlink read and read-only write. Exact bytes, Unix modes and unchanged post-denial content distinguish policy from absence/DAC. Landlock per-access events are not assumed.

Network policy grants only the fixture's exact hostname, Service /32, TCP5678 and canonical curl binary, with explicit GET/POST REST allow rules and enforce. Verify full/base/global policy, absence of providers and loaded native revisions. Native policy set --wait narrows to GET and then removes the endpoint; never treat stored-but-unloaded policy as effective. Scoped native ocsf_json_enabled=true improves attribution without changing enforcement. Setting storage acknowledgment is insufficient: observe the supervisor’s native true-setting change followed by its atomic JSON logger toggle within a separate 30-second setup budget before traffic. Transparent socket denial needs a new matching native policy event (destination/port/curl and policy-denied stage), not merely a curl error. HTTP method denial needs the native structured policy response. Read-only log polling has a separate bounded observation budget and never retries workload operations.

Successful trusted GET/POST/server-marker controls bracket negative windows. Unique denied markers must be absent while every successful marker is present. Inspect actual generated workload NetworkPolicy and independently probe its outer CNI fence from the workload pod as a trusted operator diagnostic; kubectl is never substituted for SDK workload execution. Native SDK results and supported CLI calls retain host receipts. Unknown delivery stops dependent checks.

Delete only the original native ID, use expected-ID wait and verify original CR/pod/PVC/PV disappearance. Dedicated endpoint namespace and gateway/private state/forward cleanup must complete. Require final policy.json, gateway.json, cleanup.json, fixture cleanup, JUnit and identity-checked kind teardown before a pass. Require all three complete repetitions, each in fresh control/restrictive sandboxes with its own endpoint and gateway cleanup. Repeat final source on a second fresh cluster; retain failures and earlier source attempts separately. Internal RPC/controller retries are unknown; bounded evidence does not establish general escape resistance, production tenancy or fleet reliability.

Primary references: [immutable policy schema](https://github.com/NVIDIA/OpenShell/blob/e1f3c82caa3ed3b65de22889ae7ef32a774878ef/docs/how-it-works/policies/schema.mdx), [policy commands](https://github.com/NVIDIA/OpenShell/blob/e1f3c82caa3ed3b65de22889ae7ef32a774878ef/skills/openshell-cli/SKILL.md), [transparent enforcement](https://github.com/NVIDIA/OpenShell/blob/e1f3c82caa3ed3b65de22889ae7ef32a774878ef/crates/openshell-supervisor-network/src/proxy.rs).
