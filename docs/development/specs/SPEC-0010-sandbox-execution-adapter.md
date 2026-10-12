---
id: SPEC-0010
kind: spec
title: Sandbox execution adapter
status: accepted
updated: 2026-10-12
related: [PLAN-0012, SPEC-0009, ISSUE-0005]
---

# Sandbox execution adapter

## Goal and scope

Add one vendor-free execution port over the admitted lifecycle handle. Follow [execution/recovery](../../execution-and-recovery.md) and Milestone 2. This component accepts an argv tuple and operation UUID; operator configuration owns TLS, workspace/owner, workdir, output budget, execution deadline, host deadline and worker memory ceiling. No transfers, artifact store, agents or durable orchestration in this slice.

## Boundaries and design

Pinned OpenShell v0.1.3 SDK exec_stream accumulates output before yielding and joins it at completion. A report-only clip cannot bound an unconstrained consumer. A spawned host worker uses the supported SDK, stops at the combined byte cap, and runs under Linux RLIMIT_AS and single-CPU affinity before channel creation. The selected host uses GNU glibc 2.39; its documented process-local mallopt(M_ARENA_MAX,2) limits allocator arena reservation before any native client thread starts, under the unchanged memory cap. Reject unsupported libc/profile or pre-existing worker threads. See ISSUE-0005 for the observed native allocation gap and [GNU 2.39 API](https://sourceware.org/glibc/manual/2.39/html_node/Malloc-Tunable-Parameters.html). No system allocator, library pin or parent environment is changed. The parent consumes bounded bytes and supervises a wall deadline. This minimal process supervision is justified by that observed SDK gap; it creates no protocol, retry engine or scheduler. Native execution timeout remains enabled. Close the native client on output overflow; host worker termination never proves remote cancellation.

Before exec, require original native ID/name/workspace/owner/creation-operation labels and Ready. Native operations remain name-based: require the same exclusive workspace and nonreused names as SPEC-0009. No concurrency guarantee against external replacement. Persist exclusive host intent before starting the worker; an intent without an authoritative result means unknown delivery. Preserve native errors, terminal code, retained bytes, worker identity/exit, elapsed time and cleanup status. Journal loss must retain the in-memory result. No automatic retry. Terminal codes 74/124 cannot establish normal remote completion (they can be synthetic native statuses). Successful exec is not application-fix evidence. Timeout/output/client loss requires original-sandbox cleanup or operator reconciliation.

## Acceptance and validation

Run smallest offline contract tests and repository guards before live work: identity refusal, operation reuse, output overflow, worker loss, host deadline, native error/status, storage failure and memory-limit enforcement. Qualify real bounded success/nonzero/timeout/continuous output and refusal on two fresh admitted nodes; verify mandatory storage/kernel/CNI/gateway controls, pinned workload and policy, every original resource/storage/container identity and complete fixture/cluster cleanup. Keep all failed attempts. Freeze sources before live dispatch and bind receipts to them. Record counts/latency and unavailable native internal retries/RPC counts honestly. Worker/controller crash during dispatch and production concurrency remain unqualified unless actually exercised.

## Decisions and open questions

Current user continuation authorizes this next bounded component and tracked draft publication. Transfers and immutable artifact/source storage are subsequent independent slices. Retain current immutable runtime tuple; primary release APIs still select OpenShell v0.1.3 and Agent Sandbox v1.0.6; latest Helm v4.3.0 does not invalidate the admitted pinned 3.22.0 tuple. Context7 provides discovery; pinned installed/source bytes and native receipts decide behavior. Operator budgets are local resource controls, not latency SLOs.

## Additional existing-adapter qualification

The user authorized parallel remaining-qualification work. Extend evidence for unchanged admitted components: (1) exact completed bounded native stdout/stderr into LocalArtifacts, independently read by a fresh host process after original sandbox cleanup, with separate corruption/no-overwrite refusal; (2) actual loss of the original owned SDK worker after independent remote start, requiring unknown delivery/completion, no replay and original sandbox teardown; (3) actual result-receipt directory permission refusal after independent native start proof, retaining the in-memory native outcome/output and confirmed worker cleanup. Require fresh protected roots, original directory identity, dedicated test markers/evidence roots, two fresh admitted nodes, frozen source and complete native/gateway/cluster cleanup. No output artifact is admitted from unknown execution.

These checks cover bounded synthetic execution output, original SDK-worker loss and real host result-storage failure. They add no source materialization, workload-file download, product orchestration or new domain API. Untrusted download, source-to-sandbox integration, controller crash, storage durability faults and command cancellation remain separate gates. Worker-loss signalling requires supported original-process identity; unsupported host APIs cannot be replaced with name-based killing or a new signal runner.

## Original transport interruption candidate

One separate qualification case may interrupt the original owned gateway port-forward after independent operation-marker/PID/start-time proof of remote execution. Verify its original Popen identity and exact argv, terminate and reap it through supported process methods, and preserve actual native transport detail with unknown delivery/completion. The candidate requires native UNAVAILABLE: [gRPC Core's status table](https://grpc.github.io/grpc/core/md_doc_statuscodes.html) maps a TCP break after transmitted data to that client status. Other RPC errors, cancellation or host deadlines do not pass this transport-loss oracle. Do not replay execution. Restore only the documented forward on the same endpoint so existing original-ID lifecycle cleanup can proceed; register the new original process with the existing fixture for teardown. Remote observations after reconnect are facts, not cancellation guarantees. Require worker reap, authoritative intent/result attribution and original resource/storage/task/transport/cluster cleanup on two fresh mandatory-admitted nodes. This does not qualify controller crash, storage durability, cancellation or concurrency.

## Fresh-process receipt observation

Extend the existing actual worker-loss/result-EACCES case after each original sandbox/resource cleanup. One isolated stdlib host process independently opens the original mode0700 receipt root and mode0600 regular files using no-follow descriptors, verifies original root/file identities, bounds each receipt read to16384 bytes, and binds the persisted operation/handle. Its inputs are selection and original identities only; no parent in-memory terminal receipt/output is supplied to the reader. The persisted unknown worker-loss control is read from disk; output fields are not interpreted or emitted.

The persisted worker-loss control must retain unknown delivery/completion and confirmed original worker reap. In the actual EACCES case, the new process observes only the original intent and absent authoritative result, so it retains unknown delivery/completion and refuses replay even though the original parent observed native terminal0. The initial intent's not_dispatched value is preparatory state, not proof that execution was never dispatched. Preserve the parent's separate actual native outcome/EACCES evidence, restored original directory, observer/worker cleanup and zero replay.

Require meaningful local fresh-process identity/refusal controls, actual marker discovery, unchanged operator execution budgets, a complete new source/dependency/runtime freeze and two fresh mandatory storage/kernel/CNI/gateway-admitted nodes. This qualifies independent persisted-receipt observation only; no production reader/reconciliation API, controller crash, storage power-loss/durability, cancellation, concurrent tenancy or restart orchestration is admitted.

The 2026-10-12 qualification passed the extended existing case on two distinct fresh mandatory-admitted nodes under unchanged pins, policy, TLS, kernel profile and execution limits. Four isolated readers retained unknown delivery/completion without replay, after original sandbox/task deletion; both original clusters and all original resources/processes were confirmed absent. See the [scoped qualification report](../../qualification/openshell-adapter-execution.md). These observations qualify the frozen qualification helper and existing adapter evidence, not a production recovery service.
