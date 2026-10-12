# Native OpenShell lifecycle qualification

Scope: bounded 1C on an explicitly owned single-node Linux amd64 kind cluster. Read [the milestone](../openshell-milestone.md), [SPEC-0005](../development/specs/SPEC-0005-openshell-lifecycle.md) and the [qualification record](../qualification/openshell-lifecycle.md). The application adapter, agents, policy matrix, toolchains and recovery are separate gates.

## Explicit preparation

Use the immutable tool/image tuple in [runtime-lock.yaml](../../deploy/runtime-lock.yaml) and SDK/dependencies in [uv.lock](../../uv.lock). The official v0.1.3 SDK wheel requires Python >=3.11; this project uses 3.12. Never replace the selected URL/hash with a development alias. Matching CLI/chart/controller/kernel admission is mandatory; a Python import is only an offline capability check.

```sh
uv sync --locked  # explicit dependency preparation, if not already installed
UV_OFFLINE=true make test-config
make tools
make admission-artifacts
make kind-up
# Wait for successful completion of each native command before the next.
make admission-install
make qualify-network CORSAIR_QUAL_RUN=.runs/lifecycle-network-NEW
make qualify-admission CORSAIR_QUAL_RUN=.runs/lifecycle-admission-NEW
make openshell-install CORSAIR_ADMISSION_RUN=.runs/lifecycle-admission-NEW
make qualify-lifecycle CORSAIR_QUAL_RUN=.runs/lifecycle-host-NEW
make kind-down
```

Use a new nonexistent evidence directory per attempt. Duplicate 1C paths are rejected before pytest/JUnit writes. Commands are explicit; pytest does not install or create a cluster. Gateway installation consumes successful exact-node storage/kernel admission whose runtime lock matches current source. If any prerequisite fails, do not run dependent work. Preserve every attempt and delivery uncertainty, inspect ownership before cleanup, and do not blindly retry a possible side effect.

## Native behavior and evidence

The shared pytest gateway fixture first runs bounded 1B controls: version/auth, verified trust/hostname rejection, no-client-identity rejection, actual generated pod/CR identity and mounts, plus reachable controls and direct workload CNI gateway denial. It removes the inert identity sandbox and confirms its original CR/pods absent before yielding access. Operator mTLS files stay mode 0600 under .state/openshell; credentials and ambient environments are never receipts.

SandboxClient uses an explicit verified TlsConfig and endpoint, workspace default, fixed inert native protobuf spec with pinned image/limits and the existing hard-requirement policy. Three sequential fresh sandbox repetitions check Ready (Completed is not accepted), ID/configuration binding, empty providers, generated identities, exact separated stdout/stderr/exit 23, explicit workdir/environment/stdin read/write, and a tiny binary transfer under the native discovered workspace root. CLI --no-git-ignore authorizes only that synthetic file under the ignored evidence directory; it does not upload repository/state contents. Native CLI upload/download is used because curated Python SDK transfer methods are absent.

SDK operations retain timestamps, elapsed time, explicit nonsecret arguments, typed results and native structured errors in sdk-NNNN.json; native subprocesses retain command-NNNN.json. An exception before acknowledgment records completion unknown. The native CLI owns its supported bounded transport transfer retries; the harness adds no retries. Internal RPC/poll/retry counts are unknown; host calls and latency are observable. No model/provider calls occur.

Deletion compares current native ID, checks the returned deletion ID/outcome, uses wait_deleted(expected_sandbox_id=original), then independently requires an empty workspace list and original CR/pod disappearance. Native per-sandbox workspace PVC/PVs require UID-bound reclamation before another repetition; final gateway namespace/remaining PV teardown checks immutable identities separately. Final gateway.json/cleanup.json and pytest/JUnit must agree before claiming a pass. lifecycle.json alone is provisional until fixture teardown and cluster cleanup are confirmed. Check final absence of owned fixtures/private state/forward processes, then repeat required gates on a second clean cluster.

## Failure attribution

- Calico/not-Ready or absent admission: platform/preflight; no lifecycle qualification.
- SDK import/schema or incompatible pinned artifacts: dependency/capability; no native runtime claim.
- Native TLS/auth/identity rejection: gateway/boundary admission; no fallback.
- Missing exec exit event or native RPC exception: execution/transport, delivery unknown; never interpret as expected exit 23.
- Exact output/digest mismatch: assertion/transfer; retain both native receipts and file digests.
- Original ID replaced, accepted deletion without absence or resource cleanup timeout: cleanup unconfirmed; stop repetition and reconcile before any new mutation.

See native [Python SDK](https://github.com/NVIDIA/OpenShell/blob/v0.1.3/docs/sdk/python.mdx), [implementation](https://github.com/NVIDIA/OpenShell/blob/v0.1.3/python/openshell/sandbox.py) and [CLI commands](https://github.com/NVIDIA/OpenShell/blob/v0.1.3/skills/openshell-cli/SKILL.md). Never use kubectl as a substitute command/transfer backend to obtain a pass.
