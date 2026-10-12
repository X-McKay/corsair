---
id: HANDOFF-0021
kind: handoff
title: OpenShell parallel admission qualified
status: recorded
updated: 2026-10-11
related: [SPEC-0010, PLAN-0012, SPEC-0011, PLAN-0013, ISSUE-0006]
---

# OpenShell parallel admission qualified

## Verified state

Branch `codex/openshell-parallel-admission`; clean published base/source revision `c0044c958d62d0cff20eca9169f522ab65dc83da`. Native GitHub data confirms parent [draft PR14](https://github.com/X-McKay/corsair/pull/14) remains open/draft at that exact head on `codex/openshell-source-upload`. Its exact-head development CI run 38190330413 passed with actual log 148 checks / 5.20s before editing. This handoff is prepared with the tracked changes; resolve its publication revision using `git log -- docs/development/handoffs/HANDOFF-0021-openshell-parallel-admission-qualified.md` and verify the resulting draft's exact head/native CI. No future commit SHA is invented.

The user authorized sub-agents and existing tracked stacked draft publication. Three agents worked independently on the fixed source consumer, actual transport loss and primary upstream/admission review. They cross-reviewed candidates and separately audited raw evidence. Root alone operated live clusters, maintained shared records and publishes the reviewed diff. No product adapter, port, runtime profile, image, policy, TLS setting, pin, kernel requirement or execution budget changed.

Delivered qualification-only cases:

- [Fixed source execution/output](../../qualification/openshell-source-execution.md): exact committed five-file tree from a private bare Git fixture, separate admitted staging copy, one documented native upload and one bounded native stdlib execution, captured input/recipe/runtime/image/effective-policy binding, exact output artifacts, post-execution source checks and fresh host source/output reads after cleanup. Actual operator corruption is refused before a second dispatch. Approved test-patch set is empty; no issue discovery, security comparison or fix verdict occurs.
- [Original-forward transport loss](../../qualification/openshell-execution-transport.md): independent actual remote PID/start-marker proof, original owned native Popen termination/reap, strict native UNAVAILABLE with unknown delivery/completion, no replay, original worker reap before supported native reconnection, honest remote-process observation and original cleanup. Client/worker loss is not cancellation proof.

The frozen 71-input source-v1 manifest SHA256 is `82673a4a3b4803341fa77d91704eb2c11c58c54c353999d3f7b420354f065048`. Source case SHA256 `2673708ff1077c812b76c56d9357250c290979c4037d0b121eed7f2070725ad9`; transport case SHA256 `708a85c08b0aa9caf8948a4771172af4ec76d660f7386dea4ba7a643ff461840`. Every current and frozen input still matches after both cluster deletions. Native 1A–1F and previous upload/source-arrival/execution/output/worker-loss/EACCES qualifications remain unchanged.

## Validation and blockers

Smallest relevant pre-live checks: baseline 148 / 4.52s, work-record guards 4 / 0.03s, final pre-live 148 / 4.55s, actual dedicated 2-of-18 qualification collection and diff check passed. Two real host capture/verifier/artifact-reader preflights and original Popen/marker/mismatched-identity refusal preflights passed. The 14 unchanged execution contracts passed. Host preflight and collection are preparation, not runtime qualification.

| Fresh node | Actual storage/kernel | Actual CNI | Source execution | Transport interruption |
| --- | --- | --- | --- | --- |
| fd636bd2-0789-4168-a748-87c27486d82a | 1 pass / 93.057s | 3 passes / 155.521s | 1 pass / 96.122s | 1 pass / 254.048s |
| f982d064-9408-4506-b2ad-766d5366b07d | 1 pass / 91.830s | 3 passes / 151.336s | 1 pass / 95.477s | 1 pass / 253.432s |

Actual command sequence per node: `UV_OFFLINE=true make kind-up`; `admission-install`; `qualify-admission` with new `.runs/parallel-admission-NNN`; `qualify-network` with new `.runs/parallel-network-NNN`; `toolchain-images-load`; `openshell-install` referencing that exact admission; `qualify-source-execution` with new case/network evidence roots; confirm source fixture cleanup; separate `openshell-install`; `qualify-execution-transport` with new roots; final original-owner/inventory check; `kind-down`; independent exact-CID absence. All source/transport cases passed on their first live attempt with unchanged requirements. Root and independent raw audits require actual JUnit, native controls, immutable inputs, protected receipts and original identities, rather than summaries alone.

Source totals: two uploads and two executions, application retries 0, 40 helper SDK records (38 acknowledged plus 2 expected post-delete NOT_FOUND), 18 helper probes, 7,776 helper output bytes, 215 native commands and 32 reaped capture children. Actual workload Python is 3.12.15, separate from host Python 3.12.13. Both 118-byte stdout and 25-byte stderr objects match. Core execution takes 0.108556 / 0.110079s; actual worker peak RSS 111,872 / 112,028 KiB.

Transport totals: two execution attempts and two original fault signals, application retries 0, 26 helper + 6 observer + 4 worker selected SDK calls, 234 native commands and 176 captured marker bytes. Actual core executions take 0.173210 / 0.172416s. Both original remote processes remain present with matching start ticks and unfinished markers after reconnect; no cancellation claim. Native Ready waits 141.229 / 140.228s are inside the unchanged supported 300s default. Peak RSS and internal native retry/RPC counts are unknown; no agent/model/provider calls occur.

Both mandatory kernel reports agree, including Landlock ABI 6 and all required primitives. Real storage marker bytes survive replacement pods using original PVC/PV. CNI strict denials/interleaved controls, native pinned gateway TLS/auth and original policy/image/resource admission pass. Four separate native gateway installations occur only after mandatory gate cleanup; each node's second installation follows the first gateway's complete original cleanup.

All four original application sandbox IDs, CR/pods/PVC/PV/tasks, four gateway namespaces/private state, four workers and six owned forwards are confirmed absent/reaped. Final inventories contain only the six platform namespaces and no Sandbox/PV. Exact original cluster CIDs `6f19ac25e1edaa980282201a60fadc60350ae6bb6ebf901926f54593371bb04e` and `93942387e18b2abeb9100a260b428889b48cea68bc6669f60332996653a0a3f5` were identity-checked before native deletion and independently absent afterward. Active kind owner/kubeconfig and OpenShell private state are absent. Private host fixtures, immutable objects, receipts, source snapshots and logs are intentionally retained under ignored `.runs/parallel-qualification-20261011` and the named matrix roots.

Retained preparation failures include guessed record/port paths, an initial source-reader cap, tuple/JSON normalization, early final-result ordering, import-path errors, a mismatched documentation patch and wrong PR-template casing. Cross-review narrowed an initially overbroad draft RPC oracle before source freeze. Private auditors retained wrong argv slices and an overstrict all-helper-ack assumption before correction; expected post-delete NOT_FOUND stays explicit. Transitional CNI connection failures and strict negative requests remain in native records. Root startup inventory succeeded, while two later log requests returned NotFound during teardown after original pods were removed. Those unsuccessful diagnostic reads are separate from passing matrices. No failed preparation or native attempt was deleted or relabelled as qualification.

Fresh primary release/tag/source/help review still selects OpenShell 0.1.3 at `e1f3c82caa3ed3b65de22889ae7ef32a774878ef`, Agent Sandbox 1.0.6 at `cd0761d5001baaf293460cd382ee318744d6b249` and admitted Helm 3.22.0 despite latest Helm 4.3.0. Context7 assisted discovery; immutable primary source governs actual behavior. Pinned native download still extracts all members before final status/type admission, without pre-extraction aggregate-byte/member/inode limits or supported retry-off/authoritative reconciliation. [ISSUE-0006](../issues/ISSUE-0006-native-transfer-retry-admission.md) remains blocked. No untrusted download or custom extractor was attempted.

Closing offline checks after the final records: `UV_OFFLINE=true make test-config` passed all 148 in 4.55s; frozen source-v1 and diff whitespace checks passed. Final independent Corsair review/staged diff review and tracked draft publication/exact-head native CI are closing actions following this snapshot. They do not enlarge live qualification.

## Decisions and next steps

Keep the accepted staging-copy contract: authoritative host source/artifacts remain immutable outside workload reach; pre/post observations do not detect every transient modification. No source-image/read-only-PVC prerequisite or withdrawn Docker staging workaround is introduced. PLAN-0012's bounded transport continuation is complete; PLAN-0013 remains blocked for general transfer admission.

Next independent bounded work can qualify one concrete approved-test-patch/dependency recipe consumer or one existing-adapter controller/receipt durability fault, with its own plan, native controls and fresh-node evidence. Nonempty patches, native issue-test discovery/comparative assertions, arbitrary source/dependencies, interrupted file-transfer reconciliation, untrusted downloads, controller/storage durability, cancellation, concurrency, full Milestone 2, agents/PydanticAI/Temporal and production reliability remain unqualified. Any new transfer dependency must first resolve its native prerequisite or demonstrate a reviewed enforceable narrower contract. Do not replace the missing upstream capability with a generic repair framework.

Only tracked authorized changes may enter the stacked draft above PR14. Preserve `.runs/`, `.state/`, credentials and raw logs outside Git. Current authorization covers tracked draft publication, not merge, deployment, external issue closure or upstream messaging. Closing offline/diff review and exact-head CI are publication checks, not live qualification.

## Continuation prompt

```text
Continue X-McKay/corsair. Read AGENTS.md, README.md and docs/development/CURRENT.md, the Corsair development/review/handoff skills, HANDOFF-0021 and linked PLAN-0012/0013, SPEC-0010/0011 and ISSUE-0006. Inspect branch/status/source and current primary releases; verify published exact-head CI and retained two-node qualification evidence rather than treating this handoff as proof. Use independent sub-agents for separate bounded qualifications and keep one live runtime owner. Select one next approved-recipe consumer or controller/receipt durability case; update its focused plan and run the smallest offline/preflight checks before live work. Every fresh node must pass actual storage/kernel/CNI/gateway admission. Preserve unknown delivery, original identity cleanup, immutable authoritative inputs, pins, TLS, policy, kernel and resource requirements. Untrusted extraction and general transfer reconciliation remain blocked until a supported enforceable native prerequisite or concrete narrower contract is admitted. Do not integrate agents/Temporal or claim full qualification from these fixed fixtures. Retain all failed attempts and raw evidence privately, review final scope/diff, update reports/work records/current index, append a handoff and publish tracked-only stacked draft changes within existing authorization.
```
