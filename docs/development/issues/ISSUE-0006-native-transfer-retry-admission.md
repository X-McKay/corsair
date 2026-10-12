---
id: ISSUE-0006
kind: issue
title: Native transfer retry and resource admission
status: blocked
updated: 2026-10-11
related: [SPEC-0011, PLAN-0013]
---

# Native transfer retry and resource admission

## Observed and expected behavior

Expected application native transfer admission distinguishes unknown mutation and bounds host extraction/resources. Pinned OpenShell0.1.3 automatically re-enters complete upload/download operations on selected errors, including errors after possible mutation, and does not expose a transfer byte quota or retry-off flag. This is an upstream capability/admission gap, not an observed live application failure or policy denial.

## Reproduction and evidence

[Exact source](https://github.com/NVIDIA/OpenShell/blob/e1f3c82caa3ed3b65de22889ae7ef32a774878ef/crates/openshell-cli/src/ssh.rs): lines64–65 fix four attempts/2s delay; sandbox_sync_up_files, sandbox_sync_up and sandbox_sync_down all call retry_sandbox_sync. Lines1818–1863 show whole-operation retry and substring matches including ssh tar extract exited and failed to extract tar archive from sandbox. Native download archive.unpack precedes child status; directory extraction creates/merges directly at the selected host destination. Upload extraction detects some type changes but is explicitly nonatomic. Native source path canonicalization does not establish atomic source/destination identity or byte limits.

Installed CLI SHA256557f8e2af1d91221211bb29cc7152d975084d2a8c9ab8c549d46c4370ccf492e matches runtime lock. ssh.rs SHA25604ec7f978ec01b57c271819a4c078089e838f7df8032f61fc61cf898bedb0e87. Actual sandbox upload/download --help has no retry/resource control. Private source/help/hash audit retained in .runs/transfers-storage-resume/native-transfer-source-audit.json. Curated installed Python SDK inspected; no transfer methods. Primary releases still OpenShell0.1.3/Agent Sandbox1.0.6. Context7 main docs are discovery only; GitHub web open initially failed; the closing native GitHub contents API at the exact pinned commit returned byte-identical ssh.rs, independently verified against the cached archive source.

## Attempts and diagnosis

Initial investigation used read-only source/help and earlier published execution audits only; no upload/download or cluster was dispatched at that stage. Do not manufacture a failure by risking arbitrary extraction merely to prove a visible source capability gap. Native1C's successful transfer controls remain valid for their original scope, without unknown-delivery/fault/byte-limit admission. No supported no-retry alternative found; no speculative wrapper/SDK patch adopted.

Subsequent [controlled native upload qualification](../../qualification/openshell-native-upload.md) passed on two fresh admitted nodes: trusted fixed1MiB bytes into new isolated scratch, native success plus original identity/digest admission, corruption detection and full cleanup. It permits native-owned retries only inside that exclusive disposable fixture, with zero outer retries and no authoritative artifact publication. The initial missing gateway fixture import failed before transfer dispatch and remains retained. This resolves the narrow documented-upload baseline, not this issue's broader application retry/resource criteria. Native untrusted downloads, interrupted transfer and application adapter admission remain blocked. The withdrawn Docker staging experiment is not a required prerequisite or a qualified workaround.

## Resolution criteria and next action

Require a compatible immutable supported release offering no-retry/authoritative operation reconciliation and enforceable bounded transfer/extraction, or a specifically reviewed safe narrower contract supported by actual native semantics. Requalify affected runtime/transfer boundaries with fresh nodes and negative paths before resolving. Independent local immutable source/artifact store may proceed. Do not close an external issue or contact upstream without authorization.


## Parallel qualification and native download review

Fresh primary release/source/help review reconfirms the selected runtime tuple. Native single-file download stages in a temporary directory and requires a regular expected basename before rename, but extracts all archive members first. It supplies no aggregate-byte/member/inode quota, exactly-one-entry admission or supported retry-off/reconciliation; whole-operation attempts remain four. Digest checks and host deadlines cannot bound extraction or freeze concurrent writers. ISSUE-0006 stays blocked for untrusted workload files and application transfer recovery. See [pinned implementation](https://github.com/NVIDIA/OpenShell/blob/e1f3c82caa3ed3b65de22889ae7ef32a774878ef/crates/openshell-cli/src/ssh.rs).

Already bounded completed ExecutionReceipt stdout/stderr can enter LocalArtifacts directly, without downloading files. That existing-component composition and actual host worker/receipt failures are separate PLAN-0012 qualifications; corrected full native1F is independent PLAN-0009 work. Do not add a trusted download merely to accrue passing checks or resume the withdrawn staging profile. Concrete source-upload consumer/writer admission remains a next scoped review, with no new transfer runtime or generic retry framework.

## Captured-source arrival result and remaining execution gate

The reviewed narrower five-file pre-execution composition now [passes on two fresh admitted nodes](../../qualification/openshell-source-upload.md): successful GitSource capture and exact manifest/blob reread, private separate staging with executable-bit mapping, one native directory upload per node, exact remote inventory/mode/digest admission twice, actual corruption/symlink refusal, unchanged authoritative host objects and original resource/cluster cleanup. Both source/runtime matrices use identical69 frozen inputs. No general materializer/API, repository code or active workspace is admitted; failed/lost acknowledgement cannot be replayed and unknown host descendants prevent staging reuse.

This advances native source arrival without resolving this issue's untrusted extraction/interruption/reconciliation criteria. Workload-owned0400/0500 files under writable ancestors can still be chmodded/replaced during execution. The execution contract permits an admitted staging copy, with authoritative inputs outside workload reach and honest transient-integrity limits. Next qualify concrete staging-copy-to-execution input binding with frozen source/test/recipe and before/after integrity checks; no source-image/PVC seal is made mandatory. No new image/profile is adopted. Keep the broader issue blocked and all original failures/unknowns retained.

## Parallel continuation capability review

An independent sub-agent rechecked current primary release/tag identities, fresh immutable source and the actual installed CLI/curated SDK during the user-authorized parallel continuation from published c0044c9. OpenShell0.1.3 and Agent Sandbox1.0.6 remain current; qualified Helm3.22.0 is retained. Fresh pinned ssh.rs remains byte-identical. Native download still extracts all archive members before SSH status and the single-file expected-basename/type/rename check; no exactly-one-entry or aggregate byte/member/inode admission precedes extraction. Actual CLI help exposes no extraction quota, retry-off or authoritative transfer reconciliation, and the curated SDK has no transfer methods. Four native whole-operation attempts remain unchanged.

No supported untrusted-download or interrupted-transfer candidate was found, so this track remains blocked without live arbitrary extraction or a substitute trusted transfer. Private primary source/help/hash evidence and the independent published-base source-arrival audit are retained under .runs/parallel-qualification-20261011/download-agent. A compatible immutable supported capability satisfying the existing resolution criteria is required before dependent integration. Source-execution composition and existing-adapter transport-loss qualification may proceed independently; neither resolves this transfer issue.

## Fixed source-execution and transport results

The [fixed captured-source execution/output composition](../../qualification/openshell-source-execution.md) passed on two fresh admitted nodes with exact source/recipe/runtime/policy binding, one execution per matrix, post-execution integrity observations, actual corruption refusal before a second dispatch, fresh immutable artifact reads and original cluster cleanup. Its approved test-patch set is empty; it is an infrastructure fixture, not issue validation or a general source API. The separately qualified [original-forward transport fault](../../qualification/openshell-execution-transport.md) preserves native unknown execution without replay and proves original cleanup; it does not qualify file-transfer interruption or reconciliation.

Fresh primary release/tag/source/help review still selects OpenShell 0.1.3 at e1f3c82caa3ed3b65de22889ae7ef32a774878ef and Agent Sandbox 1.0.6 at cd0761d5001baaf293460cd382ee318744d6b249. Helm 4.3.0 remains latest, while admitted 3.22.0 is retained. The pinned CLI/source still lacks pre-extraction aggregate-byte/member/inode bounds and supported retry-off/authoritative reconciliation. No untrusted download was dispatched and no custom extractor/runner was adopted. This issue stays blocked; native readiness latency and the separate transport pass do not resolve its criteria.

## Untrusted-file consumer review

The user selected untrusted downloads next. Fresh primary17-blob review from published52d3ff4 confirms current immutable releases and the same CLI extraction/retry gap. Supported Python raw ExecChunk.data is binary; final ExecResult text applies UTF-8 replacement and must not be used for file bytes. The GoFiles default download transport is unavailable. Native ExecSandbox request_id fences duplicate launches in the protocol, but the curated Python exec_stream does not set/expose it and duplicate launch fencing cannot reattach consumed stdout; it does not supply file-transfer reconciliation. No raw-RPC client is added. Private source/help/release evidence remains under .runs/untrusted-download-review-20261011/upstream-agent.

SPEC-0011 now defines a qualification-only small-file consumer through existing bounded execution/output storage: fixed isolated inline recipe, descriptor-first regular-file admission and opaque raw bytes, no archive/host parser. It addresses a concrete generated-report need while leaving native CLI download, arbitrary environments, active writers, extraction and interrupted/general transfer criteria blocked. Source/design review is not live admission; actual policy/procfd, bytes/refusals, receipts and original cleanup must pass unchanged on two fresh nodes before even this narrow consumer is qualified.

## Bounded opaque-file result; general issue remains blocked

The [fixed generated-report consumer](../../qualification/openshell-untrusted-file.md) now passes on two distinct fresh admitted nodes with unchanged72 frozen inputs: raw native ExecChunk bytes via existing OpenShellExecution, four exact immutable artifacts and ten descriptor-first refusals per node, original worker/resource/cluster cleanup and independent paired raw audits. Mandatory storage/remount/kernel/CNI and native gateway TLS/auth/fence controls passed on each current node. No native archive download or host extraction was dispatched, and no application API/runner/transport/retry layer was added. Every preparation failure, CNI convergence/readiness observation and expected original post-delete NOT_FOUND read remains retained privately.

This resolves only the reviewed small inert exclusive-file recipe. Native CLI archive extraction still lacks pre-extraction aggregate byte/member/inode bounds and supported retry-off/authoritative reconciliation. Arbitrary environments/recipes, active writers, atomic snapshots, file-specific interruption/reconciliation and production consumers remain unqualified. Overall ISSUE-0006 and PLAN-0013 stay blocked; no external issue closure is authorized. Select one concrete approved report consumer over the already-qualified execution/artifact boundaries for a subsequent focused contract review, or inspect a compatible immutable upstream candidate meeting the original general-transfer criteria. Do not widen this recipe or resume the withdrawn staging profile.
