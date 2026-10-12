---
id: SPEC-0011
kind: spec
title: Native transfer admission
status: accepted
updated: 2026-10-11
related: [PLAN-0013, ISSUE-0006]
---

# Native transfer admission

## Goal and scope

Admit only supported native upload/download with bounded resources, confined regular-file paths, expected byte/digest identity and attributable delivery over the qualified lifecycle handle. Follow [execution/recovery](../../execution-and-recovery.md); operator owns pins, policy, workspace, budgets and TLS. Do not build a transfer transport or patch upstream to bypass an admission gap.

## Boundaries and design

Pinned OpenShell0.1.3 curated Python SDK has no upload/download methods. Native CLI tar-over-SSH is the supported implementation, but its retry owner must distinguish safe reconciliation from unknown mutation. Native path/symlink preservation is broader than the first application regular-file envelope. Native installed/source bytes, not Context7 main docs, determine admission. See ISSUE-0006 for the concrete source/CLI gap.

## Acceptance and validation

Require compatible supported retry control or authoritative native operation reconciliation, host transfer byte/storage limits, regular-file/type/confinement/digest checks, original identity and protected intent/result receipts. Then smallest offline contracts followed by two fresh current-node storage/kernel/CNI/gateway-admitted matrices and original-ID cleanup. Version/help/source/render or earlier native happy-path transfers do not admit this application boundary. No app adapter/live dispatch while its prerequisite is blocked.

## Decisions and open questions

Current user continuation authorizes transfers and subsequent immutable storage; this component stays blocked rather than weakening uncertainty/resource requirements. Independent local immutable storage/source capture can proceed under its own focused spec/plan. No agents, Temporal, merges or external issue messaging.

## First native operation: trusted single-file upload

Qualify the documented CLI sandbox upload --no-git-ignore with one fixed regular host file of 1 MiB, frozen SHA256 and original local file identity, into an explicit new /tmp basename of a fresh operator-owned idle sandbox. Only trusted operator fixture bytes enter this operation; no repository code or concurrent actor runs there. Preserve existing TLS/policy/kernel/pins. Reuse existing gateway/lifecycle/cleanup fixtures, not a second transfer runtime or protocol.

The native CLI remains the retry owner (up to 4 whole-operation attempts). This narrow operation admits the final regular file only after native success, unchanged sandbox/parent identity and exact size/digest checks. A failed/lost CLI result remains unknown and is never resent by application code; the original sandbox is retired using existing identity-checked lifecycle cleanup. Repeating a native write to this isolated scratch file cannot publish an authoritative artifact or execute its bytes. This does not establish native exactly-once delivery, atomic replacement under concurrency or recovery of a failed transfer.

Two fresh admitted nodes must exercise actual successful upload, independent regular-file/digest reread and detection of a deliberately changed destination, with immutable cleanup. The 1 MiB file cap comes from the already selected source-file envelope, not a performance SLO. No untrusted host extraction occurs. Native internal retry/RPC counts remain unknown unless observed. This is native controlled-upload qualification only; the application transfer adapter, arbitrary source materialization, untrusted downloads and transport/controller loss remain unqualified. ISSUE-0006's broader gate stays blocked.

## Pre-execution captured-source consumer

The next narrower contract composes successful GitSource capture, LocalArtifacts.get and one documented native directory upload. Qualify only a fixed five-file fixture: one nested directory, five regular committed blobs, a 1 MiB binary maximum, empty/quoted/Unicode paths, raw attributes and an executable-bit entry. Exact snapshot manifest and all blob references must be reread before materialization. No checkout, filters, hooks or repository code runs. Never chmod authoritative objects: separate private host files map Git100644 to0400 and100755 to0500, preserving executable meaning while removing write/group/other permissions. Root/nested directories stay0700 for native extraction/retries. These are staging modes, not exact Git worktree permissions.

Freeze every staging-tree entry's device/inode/type/mode/size/mtime/digest, plus its immediate private evidence parent's device/inode/owner/mode. Host ancestors outside that private root remain trusted operator prerequisites, without a concurrency guarantee. Use a fresh UUID basename and absent /tmp/UUID in a newly owned idle sandbox. Operator exclusivity spans host materialization, CLI SSH/proxy descendants and remote admission; no workload or concurrent writer is admitted. Native directory upload wraps the host basename and may merge partial results on its own four attempts. There is one outer invocation, no application replay and no consumer until acknowledged native completion, unchanged original sandbox/parent/host identities and two identical exact tree/type/mode/size/digest observations pass. The trusted verifier bounds reads to1MiB/file,4MiB total,5 files/2 directories and4096 output bytes.

Require actual verifier refusal of changed bytes and an unexpected symlink, source hook absence, unchanged authoritative objects, two fresh mandatory-admitted nodes and original-ID cleanup. Failed/lost upload stays unknown and retires the original sandbox. Host source/private receipts remain retained; a host timeout does not prove SSH/proxy descendants stopped, so do not remove/reuse staging while their completion is unknown. No forced-loss/cancellation/reconciliation claim, general materializer/API, arbitrary repository execution, active-workspace upload, untrusted host extraction or dependent agent/Temporal integration follows from this qualification-only composition. ISSUE-0006 remains blocked for those broader criteria.

Read-only files inside owner-writable directories do not establish source immutability after workload execution: ownership permits chmod/unlink/replacement. The [execution contract](../../execution-and-recovery.md) permits an admitted staging copy while authoritative source/artifacts remain immutable outside workload reach, and explicitly limits transient-modification claims. Next qualify the concrete native staging-copy-to-execution input binding: freeze source/test/recipe, check relevant bytes before/after execution, invalidate observed production-source changes and preserve unknown delivery. No stronger read-only image/PVC prerequisite is introduced.

## Fixed staging-copy execution consumer

The parallel continuation selects an infrastructure-only five-file Python stdlib fixture, with no generated issue tests or application-fix verdict. Freeze its successful captured commit/tree/manifest/blobs, empty approved-test-patch set, input bytes and exact native recipe. Bind the admitted Python image/dependency state, effective policy, original sandbox identity and existing execution limits. Separate staging preserves authoritative host objects; use the documented upload and existing bounded OpenShellExecution and LocalArtifacts components.

Require complete expected input admission before one actual source command, exact small stdout/stderr and terminal status, post-execution source/recipe integrity, unchanged authoritative object identities, protected input/execution/output receipts and a fresh host output reread after original cleanup. Deliberate operator fixture corruption must be refused before any subsequent execution; prove no second dispatch. Two fresh mandatory-admitted nodes and complete original cleanup are required. This qualifies only the fixed source/input/output composition: nonempty test patches, issue-test discovery/comparative security assertions, arbitrary recipes/dependencies, source sealing, concurrency and general downloads/recovery stay unqualified.

## Bounded untrusted-file collection consumer

Collect one small generated report as opaque bytes through supported native ExecChunk.data, the existing bounded OpenShellExecution receipt and LocalArtifacts. Native CLI download remains blocked because it unpacks an unbounded archive before validation; this consumer performs no archive extraction. Its reviewed qualification recipe is operator-owned inline Python, not code loaded from the selected file or working directory. Keep the admitted runtime/policy/TLS and existing combined4096-byte output,2s native,20s host and512MiB worker limits. Bind the original inert sandbox, empty native user/provider environment and isolated interpreter startup; no arbitrary shell environment is admitted.

Select one literal direct basename under an original private UUID directory. Open the root and entry using Linux O_PATH/no-follow descriptors, check original root identity and regular-file/single-link/owner/size before reopening the admitted inode through its internally derived /proc/self/fd descriptor. Read at most4097 bytes, buffer until all checks finish and refuse overflow or observed metadata changes before emitting bytes. Following that trusted descriptor link is deliberate; sandbox-supplied symlinks, directories, devices, FIFOs and hard links are not admissible. No downloaded content is interpreted or executed on the host.

Publish only acknowledged terminal exit0 with confirmed original worker cleanup and protected original-handle intent/result receipts. Any failure, partial output or unknown result prevents publication and replay. Require actual empty/binary/exact-cap and literal-name/import-trap controls, type/link/root/path/oversize refusals, immutable host storage with corruption refusal and fresh reads after original cleanup, on two fresh mandatory-admitted nodes. This is a qualification-only fixed recipe using existing components, not a production download API. Bytes describe the captured sequence; an immutable artifact does not make their contents trustworthy or prove an atomic file snapshot. Concurrent writers, general downloads, extraction, interruption/reconciliation and dependent agent/Temporal integration remain unqualified under ISSUE-0006.
