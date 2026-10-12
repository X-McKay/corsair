# OpenShell lifecycle adapter qualification

Date: 2026-10-11. **Qualified for this bounded lifecycle slice: three real cycles on each of two fresh owned nodes with confirmed cleanup.** [SPEC-0009](../development/specs/SPEC-0009-sandbox-lifecycle-adapter.md), [PLAN-0011](../development/plans/PLAN-0011-sandbox-lifecycle-adapter.md), [runbook](../runbooks/openshell-adapter-lifecycle.md). This admits only the typed create/readiness/delete and host-receipt slice of Milestone 2; this historical report excludes execution/transfers/output bounds/artifact service/agents/Temporal; the subsequent [execution qualification](openshell-adapter-execution.md) records the new bounded application slice.

## Contract and native reuse

[Vendor-free port](../../src/corsair/ports/sandbox.py) holds original ID/name/workspace/owner/creation operation. [Adapter](../../src/corsair/adapters/openshell.py) uses the pinned native create/get/wait_ready/delete/wait_deleted; native protobuf/SDK objects stay inside this boundary. Operator supplies the qualified mTLS SandboxClient, explicit workspace/owner, fixed native image/policy/resources and a protected absolute host receipt directory. Native source lacks application lifecycle journal persistence; the small exclusive fsynced intent/result journal is the only required bespoke bookkeeping. It holds the protected directory inode, snapshots the native operator spec, and records provenance/elapsed/delivery/cleanup/native error details outside workload mounts.

Every operation uses a caller UUID, and an existing intent refuses reuse before dispatch. An intent without a result remains delivery-unknown regardless of the pre-dispatch field; it is not replay permission. Failed mutation delivery is conservatively unknown and no retry is added. A result-storage failure raises a typed error retaining known original handle/dispatch and native details. Original cause is chained. Receipt persistence failures and replacement/Completed cases are offline contract tests, not claimed live fault injection.

The native default wait 300s can return Completed; adapter explicitly requires Ready and original owner/ID/labels. [Pinned SDK](https://github.com/NVIDIA/OpenShell/blob/e1f3c82caa3ed3b65de22889ae7ef32a774878ef/python/openshell/sandbox.py) delete accepts a name without atomic expected-ID condition. Adapter refuses an observed mismatch before delete, checks returned deletion ID/outcome, waits with expected original ID, then requires native NOT_FOUND. Its confirmed cleanup receipt means API-name absence only. Qualification independently proves original CR/pod/PVC/PV/container-task absence and entire gateway/private/cluster cleanup. **Scope requires an operator-exclusive workspace and unique names; a concurrent external name replacement race is not atomically prevented.** No raw protocol workaround, lifecycle scheduler, reconciliation framework or stronger tenancy guarantee.

## Actual checks

109 offline checks passed: 94 existing repository guards and 15 focused contract cases. Coverage includes Completed rejection, changed ID/owner/workspace/creation ownership before deletion, mutation uncertainty/no retries, intent-storage failure/operation reuse, result-storage loss preserving identity/native failure, deletion-response ID mismatch, post-wait name replacement, protected directory and immutable spec snapshot. `make test-config` and existing read-only pinned-action CI run both offline suites. Collection selected 1/11 live tests before dispatch.

First node 55d0bd9e-f471-45d2-96fe-03eaefb0feb5 passed current actual storage/kernel/CNI and [native readiness sample](openshell-readiness.md). A newly installed gateway passed its TLS/auth/identity prerequisite. adapter-host-001 passed 1/123.760s: three adapter cycles, 36 explicit SDK method observations. Create timings 0.173/0.161/0.161s, readiness 8.016/9.017/9.017s, delete including API absence 0.767/1.270/1.271s. All three live forged-ID handles were refused after one native get and before any delete; each original resource survived that control until its actual owned deletion.

Actual native responses are retained by the harness, never synthesized deletion results. Every cycle proves original ID and full owner labels, actual native Ready, admitted image/profile, accepted hard policy and real Python control. Operator raw SDK/CLI observations supplement rather than replace adapter behavior. Every lifecycle intent/result is read fresh from host storage; files mode 0600/directory 0700. No workload journal editing or agent/model calls occur. Internal RPC polls/retries and controller latency remain unknown; timings include host receipt persistence. Workload-side journal attack, process restart and live disk/transport faults are unrun in this slice.

## Evidence, failures and cleanup

Frozen source-v1 in .runs/lifecycle-adapter-resume binds adapter-source-hashes.json plus native inputs; independent runs-audit-001.json checks raw JUnit/SDK/result identities/Ready/config/image/cleanup. All three original CR/pod/PVC/PV/container identities disappeared; namespace/PV/private/forward fixture cleanup passed. Empty final inventory and immutable original cluster CID absence confirmed. There are no live adapter failures in node 1. The [native sample record](openshell-readiness.md) separately retains offline cache failure and pre-dispatch evidence-directory collision, including historical summary availability loss.

Historical native 1A–1F is not reclassified as application qualification. This report excludes exec/transfers/event collection, arbitrary-output/timeout contracts, immutable artifact storage/source snapshots, application workers, PydanticAI and Temporal. The next bounded Milestone 2 slice should define and qualify execution/transfer/output/failure contracts under these still-mandatory native gates.

## Second matrix, source and review

adapter-host-002 passed 1/121.952s on node c40e33c1-2e70-45e7-b7b5-54403ff071dc, with 36 explicit SDK method observations after separately passing native prerequisites and sample. All three forged-ID deletions were refused before mutation; actual original owner/ID/Ready/image/profile/policy/control and API/resource/private/cluster cleanup passed. Both matrices used byte-identical adapter, port, unit/live test and native input hashes.

| Run / cycle | Original native ID | Create seconds | Ready seconds | Delete/API-absence seconds |
| --- | --- | --- | --- | --- |
| adapter-host-001/1 | 0c754dab-9516-4f5e-a89c-e4e8f5442d2e | 0.173 | 8.016 | 0.767 |
| adapter-host-001/2 | 1739eebc-b45d-46f6-850e-648a646ff8ba | 0.161 | 9.017 | 1.270 |
| adapter-host-001/3 | 31637532-f9f0-4f7a-b9c8-e975bbc420bb | 0.161 | 9.017 | 1.271 |
| adapter-host-002/1 | 2c529517-6929-4f31-8ce7-0b48e582c7c6 | 0.165 | 8.016 | 0.766 |
| adapter-host-002/2 | 3acc80f2-2af0-4ef4-85d7-b9e75cb58f18 | 0.160 | 8.015 | 1.272 |
| adapter-host-002/3 | 1cfa2fc8-c20b-4cbf-a4ac-455901989a36 | 0.157 | 9.016 | 1.273 |

| Qualified source | SHA-256 |
| --- | --- |
| src/corsair/ports/sandbox.py | 1032d96c5d616ea25529555ead30618b5cf1c72dbe84d1bfaefe5d4d43cae08e |
| src/corsair/adapters/openshell.py | bdfa6692a004ff2f735f4d238f6d7c23d191bcc14c233a73caf5288d8e2d50c4 |
| tests/qualification/test_adapter_lifecycle.py | a0fbed597409341e5ad4a3c6545558e0053650265fd1967823d6be8f4ce41d02 |
| tests/unit/test_sandbox_lifecycle.py | f403c9b38325c608249f264fa4692e7ac35ae6fc47a19e1b198222e4de9aa80f |

Independent raw/source audits confirmed both distinct node IDs, all six original sandbox/CR/pod/storage/container identities, 36 method observations per matrix and complete fixture/private/cluster cleanup. No live native or adapter failure occurred in the new counted runs. Final Corsair review found no blocking finding in this slice; the name-based deletion race and unrun worker/storage-fault and journal-attack coverage remain limits. Only the stated operator-exclusive lifecycle boundary is admitted.

## Subsequent shared journal consumer

The execution slice extracts the same inode-held, exclusive mode0600/fsynced writer into ReceiptDirectory, justified by a demonstrated second consumer. Current lifecycle source is re-exercised through six actual create/readiness/delete cycles in execution-host-004/005, with original identity/resource/fixture/cluster cleanup. All 15 lifecycle contract cases still pass within the 123 offline suite. This does not rewrite the original matrices or source hashes above; the [new report](openshell-adapter-execution.md) binds current source and scope.
