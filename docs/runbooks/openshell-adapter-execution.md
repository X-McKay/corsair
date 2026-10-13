# Bounded OpenShell execution adapter

Read [the execution specification](../development/specs/SPEC-0010-sandbox-execution-adapter.md) and [qualification report](../qualification/openshell-adapter-execution.md). This port is held by trusted operator code, not exposed as unrestricted agent authority. The current scope is synchronous execution over an admitted lifecycle handle, with no stdin or workload environment injection. Host mTLS credentials stay in the worker; they never enter workload arguments or mounts.

Create a user-owned absolute mode0700 receipt directory. Configure OpenShellConnection with explicit endpoint and complete CA/client certificate/key files from the qualified native gateway. Supply workspace, owner UUID, absolute workdir and immutable ExecutionLimits. No active-context discovery, plaintext fallback, TLS bypass, retries or workload-adjustable limits. The adapter uses multiprocessing spawn, so invoke application entry points under the standard Python `if __name__ == '__main__'` guard. Use the same admitted exclusive workspace and original SandboxHandle as the lifecycle adapter.

Call execute(handle, argv_tuple, operation_UUID) once per distinct operation. Intent is fsynced before worker start. The result contains exact retained stdout/stderr bytes, terminal/native error information, delivery/completion, worker identity/exit/cleanup, method observations and wall time. Nonzero ordinary terminal exits are returned for callers to classify. Output overflow, host deadline, native special status 74/124, worker/native/storage failure raise ExecutionError with the best authoritative receipt. No terminal result means unknown completion. Intent without a result also means unknown; its initial not_dispatched field is not proof after a controller crash.

The spawned Linux worker requires GNU glibc 2.39 and a single-threaded start, applies documented process-local mallopt(M_ARENA_MAX,2), single-CPU Linux affinity and hard RLIMIT_AS before opening the SDK client, checks native ownership/Ready and uses supported exec_stream with an explicit native timeout. It consumes at most the output budget plus the first overflowing native frame, sends only retained bytes, and closes the client at overflow. The parent enforces its own wall deadline and reaps the exact child, allowing at most two seconds for join/kill cleanup after supervision ends. Hard address-space limit is not an RSS target or remote process limit. Remote processes remain subject to the admitted workload profile. Native SDK internal polls/retries and physical RPC counts remain unknown; explicit get/exec_stream calls are recorded separately. Peak worker RSS is reported at a normal terminal/overflow event only; unavailable after worker loss.

Never infer remote cancellation from closing the client or killing the host worker. Reconcile the original native sandbox and use the admitted lifecycle delete path; independently confirm original CR/pod/PVC/PV/container identities and fixture cleanup. Do not replay an unknown command. Result persistence failure retains known output/identity/state in ExecutionError; preserve that receipt externally before losing the controller. Controller-loss/storage-restart recovery is not qualified by successful file reads in a normal run.

For a fresh runtime, use unique unused evidence directories and run, sequentially:

```sh
UV_OFFLINE=true make test-config
UV_OFFLINE=true make toolchain-images
UV_OFFLINE=true make kind-up
UV_OFFLINE=true make admission-install
UV_OFFLINE=true make toolchain-images-load
UV_OFFLINE=true make qualify-admission CORSAIR_QUAL_RUN=.runs/EXEC-admission-001
UV_OFFLINE=true make qualify-network CORSAIR_QUAL_RUN=.runs/EXEC-network-001
UV_OFFLINE=true make openshell-install CORSAIR_ADMISSION_RUN=.runs/EXEC-admission-001
UV_OFFLINE=true make qualify-adapter-execution CORSAIR_NETWORK_RUN=.runs/EXEC-network-001 CORSAIR_QUAL_RUN=.runs/EXEC-host-001
```

Freeze the reviewed complete source/input manifest before any live dispatch. Gateway fixtures clean their installation/private state; inspect empty final native inventory, then make kind-down and confirm the original container ID is absent. Retain every failed attempt and cleanup evidence. Read the reviewed report for the actual tuple and coverage; these commands alone establish no pass.
