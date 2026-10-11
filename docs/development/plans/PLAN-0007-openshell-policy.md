---
id: PLAN-0007
kind: plan
title: Qualify native OpenShell policy boundaries
status: complete
updated: 2026-10-11
related: [SPEC-0006, PLAN-0006, HANDOFF-0008, HANDOFF-0009]
---

# Qualify native OpenShell policy boundaries

## Objective and dependencies

Implement and qualify only [SPEC-0006](../specs/SPEC-0006-openshell-policy.md), native 1D, after the user's instruction to proceed from the 1A–1C status review. Clean base 4222a60a0eb99a65eaaa43a02e641381e5c28881 matched published open draft PR #5; branch codex/openshell-1d-policy. Actual prior lifecycle/gateway/cleanup and Service-readiness receipts were reread; absent historical original network raw logs were not claimed as re-audited. See the [qualification report](../../qualification/openshell-policy.md) for immutable identities, all attempts and actual limits.

## Steps

- [x] Verify branch/source/publication, prior native receipts and primary current release/policy sources before edits.
- [x] Implement focused native artifact preparation, policy probes and offline evidence guards.
- [x] Run smallest offline checks before live work; bind the fixed artifact and exact-node prerequisites.
- [x] Qualify the complete matrix three times in fresh sandboxes on each of two fresh clusters; confirm all original-ID cleanup and final cluster absence.
- [x] Review final diff/evidence, reconcile report/runbook/CURRENT and append handoff; prepare authorized tracked draft publication.

## Validation and progress

| Command / boundary | Actual result |
| --- | --- |
| UV_OFFLINE=true make test-config before edits | 30 passed / 0.08s |
| Focused source corrections, then make test-config before final live dispatch | 61 passed / 0.12s, including authority, missing executable, loaded policy, original-ID, logging activation and native egress-form guards |
| make policy-image | Initial canary-only preparation was incomplete for network use; two subsequent executable controls failed; final fixed Ubuntu/curl artifact passes DAC/content and actual curl invocation with original container-ID cleanup |
| make kind-up, admission-install, policy-image-load | Three clusters created in this slice; final two load the identical native manifest/config hash chain |
| make qualify-admission, qualify-network | Final nodes passed 1 storage/kernel and 3 CNI tests each, with exact lock bytes and immutable fixture/PV cleanup: 91.29s/158.59s and 91.29s/159.48s |
| make openshell-install; make qualify-policy with explicit same-node CNI evidence | Final-source policy-host-005/006/007 and 008/009/010 each passed the complete native matrix plus gateway controls and cleanup |
| Final owned inventories, make kind-down | All Sandbox/PVC/PV and owned fixture namespaces empty; all three original cluster IDs removed with confirmed absence; owner/kubeconfig/private gateway state/forwards absent |

Six policy invocations: 174 acknowledged SDK calls, 1,510 native commands, 12 distinct policy sandboxes, 30 positive and 60 denied network markers, 30 matching native JSON endpoint-denial events. Final source hashes remain unchanged across all six runs. Raw SDK responses, native server logs, method-denial detail, original identities and JUnit were audited, not just summaries. Local audits are retained under .runs/policy-resume/; raw evidence never enters Git.

Retained policy-host-001/002/003/004 failed in 80.04s/291.02s/192.42s/183.08s. Producing layers: an incorrect global-absence oracle; missing curl; JSON activation after the denied operation; and incorrect explicit-empty egress serialization expectation. All original-ID cleanup is confirmed; early run001 predates policy.json and is audited through its actual failed native receipt/no policy-create observations. Neither partial results nor earlier source count as acceptance. Two failed image/library controls, initial incomplete preparation, native diagnostic container cleanup, and read-only inspection mistakes/corrections are also retained. The report preserves their identity and reason.

## Decisions and next action

Reuse supported Docker/kind image preparation, native CLI creation/policy updates and SDK execution/deletion/expected-ID waits; no production adapter or new scheduler. Shared identity inspection gains only an explicit expected-image argument for this demonstrated second image consumer. Operator-only fixed Ubuntu/curl canaries distinguish policy from DAC/absence. No policy, TLS, upstream pin, kernel requirement or native command deadline was weakened.

Review corrected original-create identity binding, actual executable validation, exact native global absence, pre-traffic atomic JSON activation, Kubernetes omitempty egress semantics and three complete fresh-sandbox repetitions per node. No unresolved mandatory finding remains. Read-only evidence polling never replays workload commands. Native create latencies 142.29s in failed run002 and 141.55s/140.18s in accepted runs008/010 remain retained with unknown cause; they do not qualify recovery or reliability. Internal retries/queue timing remain unknown.

Publish only authorized tracked changes as a draft stacked above still-open PR #5; verify remote head and exact-head offline CI, and do not merge. Next separately bounded component is native 1E toolchain qualification. 1F interruptions/limits/recovery, production tenancy, application adapters, PydanticAI and Temporal remain unqualified. Every new node still requires actual storage/kernel/CNI/gateway admission before dependent work.
