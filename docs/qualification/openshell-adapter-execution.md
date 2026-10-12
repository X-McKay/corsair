# OpenShell execution adapter qualification

Date: 2026-10-11. **Qualified for the bounded execution slice: three full cycles on each of two fresh admitted nodes, with confirmed original cleanup.** [SPEC-0010](../development/specs/SPEC-0010-sandbox-execution-adapter.md), [PLAN-0012](../development/plans/PLAN-0012-sandbox-execution-adapter.md), [runbook](../runbooks/openshell-adapter-execution.md). This admits synchronous argv execution and protected host receipts over the qualified lifecycle handle. Transfers, immutable artifact/source storage, controller/worker-loss recovery against a live gateway, production concurrency and later milestones remain unqualified.

## Native reuse and authority

Pinned OpenShell v0.1.3 [SDK source](https://github.com/NVIDIA/OpenShell/blob/e1f3c82caa3ed3b65de22889ae7ef32a774878ef/python/openshell/sandbox.py) matches installed SHA-256 57b9450b6b514a90f994d03fdb8a2b52d3d23d35560f66e7e2100d09ec7814cb. exec_stream buffers consumed chunks and joins them at a terminal result; no arbitrary-output budget/public cancellation handle exists. Supported SDK execution runs in a spawned Linux host worker, with single-CPU affinity before channel creation, documented GNU glibc 2.39 process-local mallopt(M_ARENA_MAX,2) before any thread, and hard RLIMIT_AS. Actual host libc SHA-256 is 3a15d66867d83762c7f2f1e37359cb8f6c5743edb369c65285cb0b1c4f7498bf on Linux 6.14.0-37-generic; its native library receipt is retained ignored. Unsupported libc/profile is refused; no parent/system allocator or environment is modified. Consumption stops at the first overflowing chunk; only capped bytes cross the host pipe. Parent wall supervision and exact-child reaping bound a stalled native client. No new transport, retry engine, scheduler or agent authority.

Operator owns endpoint/full mTLS, workspace/owner, workdir, immutable limits and host storage. Native ID/name/workspace/full ownership labels and Ready are checked before exec. The qualified tuple uses 4096 combined stdout/stderr bytes, 2s native command timeout, 20s host supervision plus up to 2s cleanup grace, a 536870912-byte worker AS ceiling, one CPU and two allocator arenas on GNU glibc 2.39. These are local resource controls, not product latency SLOs. Workload policy, resources, TLS, pins and mandatory kernel requirements are unchanged. Exact binary output survives SDK UTF-8 replacement in its final aggregate because the port retains original chunks.

Ordinary terminal exits 0/7 are returned as observed outcomes. Native 74/124 can be synthetic and cannot establish normal completion. Missing terminal, overflow, host/native/storage failure remain unknown; no automatic retry. Host client closure/termination does not prove remote cancellation. The native name API has no atomic expected-ID exec/delete: require the admitted exclusive workspace and nonreused names. Every operation has an exclusive fsynced host intent/result; intent without result remains unknown. Native diagnostic type/detail/code/raw status survive the process boundary as data; live error-object chaining across workers is not claimed. Fresh host readers verified receipts, not controller-restart durability.

## Actual checks

Baseline 109 offline checks passed; final pre-live 123 passed: 94 repository guards, 15 lifecycle and 14 execution/supervision cases. Meaningful host cases cover exact binary/nonzero output, UUID reuse, owner refusal, overflow, dead/hung worker, uncertain start, native status, hard Linux excess-allocation refusal and post-terminal storage loss. Fixture events are offline contracts only. Mandatory native storage/kernel/CNI/gateway/TLS/auth/identity checks passed on each counted node. Real fixed Python workload uses the existing immutable artifact/profile/policy; no arbitrary repository or application-fix verdict is admitted.

| Run | Node UID | Admission seconds | CNI seconds | Execution matrix seconds | Lifecycle/helper methods | Worker get/exec_stream attempts |
| --- | --- | --- | --- | --- | --- | --- |
| execution-host-004 | 26fcdced-ede4-47cb-ab6c-3121f18c636b | 94.237 | 156.016 | 208.799 | 33 | 27 |
| execution-host-005 | b84127f9-e300-437e-9aba-21f762b108c2 | 93.253 | 158.585 | 217.826 | 33 | 27 |

Each matrix contains three original sandbox cycles and 15 distinct worker operations: binary success, deliberate exit 7, native 124 timeout, continuous-output overflow and forged-ID refusal. All 24 active execution workers across both nodes reported the actual hard memory/CPU/libc/arena constraints; each overflow retained exactly 4096 bytes, returned unknown completion and was reaped. Six refusals observed only get and dispatched no exec. All 30 workers exited 0 and cleanup was confirmed. Selected method attempts are separate from physical RPCs/internal SDK polls/retries, which remain unknown. No model/provider/durable work occurred.

| Mode | First matrix elapsed seconds | Second matrix elapsed seconds |
| --- | --- | --- |
| success | 0.101/0.107/0.107 | 0.105/0.109/0.113 |
| nonzero | 0.097/0.095/0.095 | 0.100/0.097/0.098 |
| timeout | 2.093/2.093/2.092 | 2.096/2.091/2.094 |
| overflow | 0.120/0.122/0.120 | 0.121/0.122/0.120 |
| refusal | 0.109/0.117/0.107 | 0.114/0.111/0.098 |

Worker peak RSS observed at terminal/overflow events: 110444–111844 KiB. Missing RSS/limit confirmation remains null, not zero; full post-event RSS peak and remote process cancellation are not inferred.

## Retained failures and cleanup

Clean source/base af87dce5b28107918d4fbcdf56628cf6f6082939, published draft PR9 at that exact head and successful exact-head CI verified before editing. Parent raw two-node JUnit/source/native identity/resource cleanup re-audited under .runs/execution-adapter-resume/parent-runs-audit-001/002.json. Current primary releases were checked: OpenShell 0.1.3 and Agent Sandbox 1.0.6 unchanged; latest Helm 4.3.0 does not change admitted pinned 3.22.0. Historical native 1A–1F and its original 120s budget are not reclassified; full corrected 1F matrix remains unrun.

Direct uv collection initially failed against read-only home cache; explicit repository cache corrected it. System Python freeze helper lacked the SDK; repository venv/PYTHONPATH froze source before live dispatch. Neither preparation failure mutated the runtime. execution-host-001 then failed fixture discovery (missing gateway import): 1 error, six read-only identity commands, no gateway qualification or execution dispatch. Original installed namespace UID and empty Sandbox inventory were checked before corrected distinct attempt 001a. Both failures remain retained.

execution-host-001a failed its first real control: 1 failed/248.243s, native pthread_create resource errors, no output/terminal, operation 401988bc-e9d7-482b-973b-7dc1532b6844 remains unknown. Exact worker 3365396 reaped at host deadline (21.023s including grace); original sandbox 57b29f55-b9f4-4e09-8337-abed47d26c82 and original resources/container tasks plus gateway/private/forward cleanup confirmed. Bounded actual-host local SDK probes reproduced allocation errors at 512MiB and 1GiB with unrestricted CPU affinity; single-CPU affinity avoided those diagnostics in the first probes at unchanged 512MiB, but the next live repetition showed it was insufficient alone. This supports an allocation/scaling interaction, not a proven detailed library/allocator cause. [ISSUE-0005](../development/issues/ISSUE-0005-execution-worker-resources.md) is resolved only by the two subsequent fresh-node matrices, not the probes. The earlier unknown operation was never replayed or reclassified.

Single-CPU source-v4 execution-host-002 passed an intermediate matrix, but execution-host-003 failed its third binary control: unknown operation c2b1e112-3b23-42fd-ab5d-b8d2e5f3a7a4, worker 3496845 reaped at the host deadline, repeated native pthread_create resource diagnostics. All three original sandboxes/resources and complete fixture/cluster cleanup confirmed. The intermediate pass does not meet two-node acceptance. Five actual-host no-credential probes using documented process-local [GNU glibc 2.39 arena admission](https://sourceware.org/glibc/manual/2.39/html_node/Malloc-Tunable-Parameters.html) under the same limits had no thread-allocation diagnostics and all exact children reaped. This supports limiting allocator reservation; detailed upstream cause and fleet reliability remain unknown. No memory/output/deadline/kernel/TLS/pin requirement was weakened.

Source-v2/v3/v4 preserve failed/intermediate attempts; source-v5 preserves allocator profile development; source-v6 adds explicit failure attribution and binds both counted execution-source-hashes.json manifests. Independent execution-audit-004/005.json check raw JUnit, actual identity/policy/image/profile, receipts and original resource cleanup. Every original CR/pod/PVC/PV/container task and gateway namespace/PV/private/forward identity disappeared. Empty final inventories and original cluster CIDs are independently confirmed for all five nodes, including both failed native-worker nodes. No live installation/private state remains. The earlier unknown operations remain unknown after cleanup. Raw logs and credentials remain ignored; only this attributable reviewed summary is tracked.

| Counted source | SHA-256 |
| --- | --- |
| src/corsair/ports/execution.py | fe2110ef5404300732648bedde60f4765f41f43a8fdd141194ac7c8bbb1d1cf5 |
| src/corsair/adapters/openshell_execution.py | cfa15a4e39b278b81d42a83825e04abccc5d50ba54f3b178ff9dffa3c088f4ba |
| src/corsair/adapters/receipts.py | 506f0b391b3fe1c5ae5230635f62d575b15091a0a7d3a6403918edd742e8092a |
| src/corsair/adapters/openshell.py | d24db2ff0cdd6f2b2047f11610b8aaa571888440677fae375227e5b4b64fb51f |
| tests/qualification/test_adapter_execution.py | c02fd7b052684de81db9ec7c54e260e3cc6cedec281cc7f40f9fd9aaf5044638 |

## Review and limits

Corsair review checked narrow vendor-free ports, supported SDK reuse, immutable operator authority, bounded host consumption, unknown outcomes/no retries, protected host journal, actual Ready/identity and distinct cleanup layers against frozen raw evidence. Shared journal extraction re-exercised create/readiness/delete six times in the counted matrices and retained all 15 lifecycle contract cases. No blocking finding remains for this slice. Live disk/controller/worker-loss and transport fault recovery, cancellation proof, journal attacks and concurrent tenancy remain unrun; offline fault contracts do not admit those external cases. Next component is native transfer/path/digest contracts, then immutable artifact/source storage. No PydanticAI or Temporal integration yet.


## Additional qualified execution boundaries (2026-10-11)

Two new existing-component cases passed on each of the same fresh admitted nodes as [corrected native1F](openshell-recovery.md). Each invocation uses a dedicated marker and new evidence root, with complete native gateway prerequisites and original fixture teardown before the next installation. Source ports, adapters, runtime pins, TLS/policy/kernel requirements and budgets are unchanged. This adds live evidence, not a transfer or retry runtime.

| Fresh node UID | Output-artifact run / pass / duration | Worker-loss + receipt-refusal run / pass / duration | Helper SDK records / native commands (output; faults) |
| --- | --- | --- | --- |
| 3c20846d-043c-4c05-8996-7152da4dacde | execution-artifacts-host-001 / 1 / 95.939s | execution-receipts-host-001 / 1 / 136.142s | 11 / 93; 23 / 139 |
| 29cb72d6-13dd-4b4a-bae2-ff978c894b36 | execution-artifacts-host-002 / 1 / 94.899s | execution-receipts-host-002 / 1 / 135.108s | 11 / 93; 23 / 139 |

Actual execution durations (node001/002): output 0.117669/0.119382s; worker loss 0.160692/0.162344s; result-storage refusal 1.623825/1.620002s. These are observations, not latency criteria.

Completed native terminal0 delivers exact1024-byte binary stdout and23-byte stderr under the existing4096-byte output,2s native execution,20s host and512MiB worker limits. Only acknowledged/terminal-observed output enters LocalArtifacts. Actual immutable references, digest/size/mode0400 and duplicate-put inode identity pass; a fresh actual host process reopens the anchored private root and reads both references after original sandbox/tasks cleanup. Separate corrupt read/put fixtures refuse and retain the original inode rather than restore valid bytes; their original fixtures are removed. Authoritative output objects remain protected private evidence. This is bounded stdout/stderr composition, not workload-file download, source staging or interrupted-output publication.

Worker-loss injection uses the unique original bounded multiprocessing Process object under an exclusive parent and supported Process.kill exactly once, after an independent native marker/PID/start-tick/sleeping observation. The unchanged remote PID/start ticks remain sleeping with no finished marker after host loss. Both receipts record host_supervision/EOFError, worker_loss, unknown delivery/completion, native exit unknown, worker exit-9 and confirmed reap. Neither receipt nor subsequent teardown proves remote cancellation. Original-process ownership is not an atomic expected-start signalling or concurrent-tenancy guarantee.

Actual result-directory refusal uses the original owned directory FD/inode, changes mode0700 to0500 after native start and observes genuine PermissionError/errno13. Native terminal0 and exact88-byte output survive in memory with worker exit0/reap confirmed. Production preserves reason=terminal and failure_layer=null, adding storage_error; the native workload did not fail. No authoritative result file is present, the intent is retained and original mode0700 restored against identity. The restart statement is a parent-observed inference: a later reader must treat intent without result as unknown delivery. A fresh receipt-reader process, controller crash and reconciliation were not tested here. No command is replayed.

Across application matrices: six original sandboxes/workers,12 selected worker get/exec_stream attempts,68 helper SDK records,464 native commands,2446 retained output bytes and12 observer execs; application attempts6/retries0 are observed. Helper counts include six expected typed post-delete NOT_FOUND responses, which independently establish native absence. Internal RPC/poll/retry telemetry is unknown; worker-loss RSS is null/unknown. Actual storage-refusal RSS and worker profile are retained in private receipts. Both new cases use the admitted Linux/glibc2.39, single-CPU/two-arena profile under unchanged hard limits.

Frozen native-source-v2 (67inputs) and application-source-v3 (68inputs, manifest SHA-2560ec18d390bda6f3f5822f9e6fd149cdc87aa5d632d8faacf3d67d2a5d456b71f) bind both runs and current source. New qualification test SHA-256 values: test_execution_artifacts.py cb5ef2175a4a4a6fc585d7dcc1c5dd1754fe2e97279a2f076035c16bf7dfe666; test_adapter_execution_storage_failure.py 7d2c24241e9fd43103a94ccc9c9af47498358a996fa28c96b79e5b3ae75d7b6d. Private raw/source/output/fault/original-cleanup audits and independently checked host process absence are under .runs/remaining-qualification/download-review and recovery-review.

Retained preparation failures include private reader/import paths, direct collection against the read-only home UV cache, unavailable pidfd APIs in the selected Python3.12.13 build, and audit snapshot-path/nullable-result/expected post-delete absence assumptions. Supported original Process and actual EACCES local preflights passed before dispatch; pidfd is a rejected test method, not an additional kernel/OpenShell requirement. No preparation failure counts as runtime qualification. Each actual live matrix passed, with original CR/pod/PVC/PV/tasks, gateway namespace/PV/private/forward cleanup and both final immutable cluster IDs confirmed absent. Valid host output evidence is intentionally retained.

Corsair review finds no blocking issue within these supported cases. [ISSUE-0006](../development/issues/ISSUE-0006-native-transfer-retry-admission.md) still blocks untrusted extraction/application transfers. Source-to-sandbox integration, controller crash, transport/storage durability faults, cancellation proof, journal attacks, concurrency, full Milestone2, PydanticAI/Temporal and production reliability remain unqualified. Commands: make qualify-execution-artifacts / qualify-execution-receipts with per-node network evidence and fresh evidence roots.148 relevant offline checks and actual marker/fixture collection passed before live work.

## Qualified original-forward transport follow-up

The subsequent [original-forward transport-loss case](openshell-execution-transport.md) passed on two fresh admitted nodes with strict native UNAVAILABLE/unknown attribution, one application attempt without replay, original worker reap before supported reconnection and complete original cleanup. This adds one bounded transport fault; broader controller/storage durability, cancellation, concurrency and transfer reconciliation remain unqualified.
