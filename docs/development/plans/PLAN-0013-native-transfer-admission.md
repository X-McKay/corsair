---
id: PLAN-0013
kind: plan
title: Native transfer admission
status: blocked
updated: 2026-10-11
related: [SPEC-0011, ISSUE-0006, PLAN-0012]
---

# Native transfer admission

## Objective and dependencies

Admit SPEC-0011's supported native application transfers after verifying actual parent source/evidence, releases and native retry/resource capabilities. Immutable local artifact/source storage is independent and can proceed if transfer admission is blocked.

## Steps

- [x] Verify clean base, published PR10/exact-head CI, two counted raw/source/identity matrices and five original cluster CIDs; inspect supported pinned CLI/SDK and current releases.
- [x] Identify retry/resource admission gap and retain attributable source/help evidence in ISSUE-0006.
- [ ] Resolve the supported native prerequisite before designing an application wrapper; run its offline and fresh-node live matrices afterward.
- [ ] Complete the dependent adapter review/qualification; retain unknown operations and original-ID cleanup.

## Validation and progress

Clean base876ca931c8049584de2e77245b0e4e6939515abb, open draft PR10 and successful exact-head CI38180796113 verified through native GitHub API. Independent raw execution004/005 audits bind source-v6,30 worker receipts and original sandbox/resource/fixture cleanup. Five original cluster CIDs freshly inspected absent; private state absent. Baseline UV_OFFLINE=true make test-config:123 passed. OpenShell0.1.3/Agent Sandbox1.0.6 still current; latest Helm4.3.0 does not alter qualified3.22.0 tuple. Context7 discovery used, pinned source and installed CLI help inspected. An initial wrong tool path failed locally before corrected .tools/linux-amd64 help; no live dispatch.

Native source fixes SYNC_RETRY_ATTEMPTS=4 and delay2s, wraps both upload variants and downloads, and retries ssh extraction/archive-unpack errors after possible writes. CLI flags expose no retry-off or transfer byte quota; curated SDK has no transfer path. Closing primary GitHub contents API verified ssh.rs byte-for-byte at e1f3c82. Source/help/hash and parent audits retained under ignored .runs/transfers-storage-resume. Application transfer adapter and fresh runtime dispatch unrun, blocked by ISSUE-0006. Prior native1C success remains historical and unchanged.

## Decisions and next action

Do not invent safe retry from repeated identical input: destination type/symlink/concurrency and partial placement are not atomically reconciled. Do not patch source, add a tar/SSH implementation, weaken TLS/policy or claim host deadline proves no side effect. Inspect an immutable upstream candidate only after it offers a supported control/reconciliation and bounded extraction. Continue PLAN-0014 independently; publication includes the blocked plan/issue, not a false transfer pass.

## Resumed investigation and course correction

The user resumed native transfer work after the principles review, then challenged the added Docker staging complexity. Current published base3ed8783/PR11 and successful exact-head CI38182853179 were verified; upstream primary releases remain OpenShell0.1.3, Agent Sandbox1.0.6 and Helm4.3.0. Context7 discovery and pinned native source/help confirm that routine single-file transfers are documented and that whole-operation retries and missing exposed byte quota remain the application admission gap, not evidence of a broken standard transfer path.

An experimental host Docker staging profile was introduced before establishing the smallest native transfer contract. It reused the qualified Python image with read-only root, bounded tmpfs, no network/credentials, dropped capabilities and read-only native binaries. This was premature additional execution-layer complexity; it is withdrawn, not a mandatory platform prerequisite. The unqualified probe is removed from repository source and its final bytes retained privately under .runs/transfer-narrow-admission/rejected-staging-probe.py. No transfer adapter, OpenShell transfer, new cluster or image was dispatched; no runtime pins/policy/TLS/kernel requirements changed.

Actual results: baseline make test-config passed148 checks; initial guessed read paths and default uv cache/import setup failed locally. host-001 failed module import before evidence directory/container creation. host-002 observed tmpfs byte/inode exhaustion and read-only-root refusal, then failed because the Python image lacks SSH. Its original CID2f1b0ebaad6f40b58480c3c3e949d70a32d01ced4ff238f062aaaa9feab2fd55 was removed; an audit incorrectly matched Docker absence-message casing and retained unconfirmed cleanup. Independent native rechecks confirm original-ID absence without rewriting the failed raw result. host-003 added a read-only host SSH binary bind and failed its native ssh -V invocation; the underlying SSH diagnostic was not retained by that check, so its exact cause is unknown. Original CID8dbda1bbf2b083601242006a42522c21fb871a269f6fa882284efc4d197ed99e has confirmed cleanup. No forced-loss case ran and no staging profile is qualified. Current owner-label inventory is empty and both original IDs are freshly confirmed absent. Private stdout/stderr/journals remain retained. Unprivileged user-namespace availability was read-probed successfully; no alternate profile was adopted.

Correct next action: define and assess one documented native CLI single-file operation on the admitted host and a freshly owned sandbox scratch destination. Keep trusted immutable upload input separate from sandbox-supplied downloads and authoritative artifact storage. Application retries remain disabled; native retries must be accounted for under the narrow contract rather than assumed safe or suppressed by an unsupported patch. Unknown completion is retained, and no downstream use follows until native completion and expected identity/digest admission pass. Downloads need their own bounded ingestion decision. Do not build a Docker/namespace transfer runner, generic reconciliation service or custom tar/SSH transport without a demonstrated unmet requirement. ISSUE-0006 stays blocked until the chosen actual native contract is qualified under the existing mandatory gates.

Course-correction validation:4 development record/link guards passed; git diff --check passed. Final diff is limited to this plan, CURRENT and HANDOFF-0017; qualified source remains unchanged and the unqualified probe is absent from repository source.
