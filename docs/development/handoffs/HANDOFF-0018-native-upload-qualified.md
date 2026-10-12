---
id: HANDOFF-0018
kind: handoff
title: Native upload qualified
status: recorded
updated: 2026-10-11
related: [PLAN-0013, SPEC-0011, ISSUE-0006]
---

# Native upload qualified

## Verified state

Started clean at2f4a4ea7ca29da18d43598a96e4087b92e7af725, published open draft PR11 with successful exact-head CI38183531997. Closing parent read confirms the same head. Current branch codex/native-upload-qualification contains this native test/Make target/marker and work records; no application runtime changes. Resolve the commit published with this handoff using git log and actual GitHub state, not a future SHA. Publication is a stacked draft above PR11 under the user's existing tracked-change authorization; no merge, external issue closure or messaging.

One documented native trusted1MiB single-file upload passed on each of two fresh storage/kernel/CNI-admitted clusters, using existing TLS/auth/identity/gateway fixtures and unchanged policy/pins/kernel requirements. [Report](../../qualification/openshell-native-upload.md) binds actual node/sandbox/cluster IDs, exact hashes and measurements. Native application transfers/untrusted downloads remain blocked under ISSUE-0006. No live cluster, OpenShell namespace, private gateway state or kubeconfig remains.

## Validation and blockers

Before live work,148 offline checks passed and1/13 cases collected. First upload matrix native-upload-host-001 failed setup because the module lacked the existing gateway fixture import; no upload dispatched. Failed JUnit/source-v1 are retained. One import fix,148 passing offline checks and actual fixture discovery preceded source-v2 freeze of66 files. Counted native-upload-host-002/003 passed1 case in121.49/94.93s, one outer CLI invocation each,15 explicit SDK observations each, two digest reads and deliberate corruption detection. Every fresh node passed1 storage/kernel and3 actual CNI cases, then gateway prerequisites. Native upload observations0.096/0.098s are not SLO criteria. Native internal retries/RPCs remain unknown; application retries zero.

Independent matrix-audit.json verifies frozen source, raw JUnit/CLI/SDK/bytes, distinct original identities and resource inventories. All original sandbox/CR/pod/PVC/PV/container-task and gateway/namespace/private/port-forward cleanup passed. Both clusters were identity-checked and deleted; closing-container-audit.json freshly confirms both original CIDs and dedicated name absent. Private evidence stays under ignored .runs/native-upload-resume and the named matrices. Withdrawn staging failures remain preserved in PLAN-0013/HANDOFF-0017, with no revived staging profile. Final review found no blocking finding for this narrow operation. Closing UV_OFFLINE=true make test-config passed148 checks in4.55s; git diff --check passed. No private evidence is tracked. Verify CI against the actual published head after publication; local qualification is not a substitute for that CI result.

Untrusted host extraction, arbitrary source materialization, application transfer adapter, transfer interruption/cancellation/reconciliation, corrected full1F and agents/PydanticAI/Temporal remain unqualified. Historical native and local artifact reports keep their own limits; this upload does not broaden them.

## Decisions and next steps

Use supported native CLI/SDK and existing fixtures. Native-owned retries are confined to exclusive trusted disposable scratch; failed/lost acknowledgement remains unknown and is never replayed by application code. No downstream use or authoritative publication follows without identity/digest admission. No bespoke runner, tar/SSH transport, generic reconciler or requirement relaxation.

Next bounded step: inspect the documented single-file download path and actual pinned semantics; identify the smallest supported bounded host-ingestion contract before accepting any sandbox-supplied bytes. Keep the broader issue blocked if enforceable extraction/resource/uncertainty admission is unavailable. Do not introduce a host staging runtime simply to fill a hypothetical gap. Application upload integration also needs its actual consumer/trust/concurrency contract reviewed; this idle trusted fixture is not that consumer.

## Continuation prompt

Read AGENTS.md, README, CURRENT, the Corsair skills, PLAN-0013/SPEC-0011/ISSUE-0006 and HANDOFF-0018. Inspect branch/status/source/current primary releases and actual published PR/CI state. Verify the two native upload matrices and all original-ID cleanup from source/raw evidence, not this handoff alone. Take only the smallest documented native download admission review: define enforceable bounded host ingestion and unknown completion before live sandbox-supplied extraction. Preserve native TLS, policy, pins, kernel gates and every failed attempt. Do not revive Docker/namespace staging or add a transfer protocol/generic retry framework. No application integration, agents or Temporal before their required gates. Run proportionate checks, update records, append a handoff and publish only tracked authorized changes; never .runs/.state/credentials/raw logs.
