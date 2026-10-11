---
id: HANDOFF-0008
kind: handoff
title: Service readiness prerequisite qualified
status: recorded
updated: 2026-10-11
related: [PLAN-0006, ISSUE-0003, SPEC-0001, HANDOFF-0007]
---

# Service readiness prerequisite qualified

## Verified state

Branch codex/service-readiness; base/source cc97b88204b92fd7e9e8621a34d9abeeba9da08c matched published open draft PR #4. Clean resume; prior failing native requests and six failed-fixture UID cleanup receipts were read. Existing original network raw evidence remains absent, as recorded previously; new retained network receipts were audited directly. Current kind/Calico release metadata matches selected 0.33.0/3.33.0. Exact immutable Kubernetes v1.35.8 proxy source and release responses are retained locally. No runtime/artifact/policy/TLS/kernel inputs changed.

[PLAN-0006](../plans/PLAN-0006-service-readiness.md) is complete and [ISSUE-0003](../issues/ISSUE-0003-service-control-readiness.md) resolved for bounded fixture admission. The [focused qualification report](../../qualification/service-readiness.md) preserves failure-time observations, final-source runs, cleanup identities and limits. Resolve the committed work with git log -1 --format=%H -- docs/development/handoffs/HANDOFF-0008-service-readiness-qualified.md; this precommit snapshot does not invent a future SHA or assert a clean precommit tree.

## Validation and blockers

Frozen baseline .runs/readiness-baseline-001/ ran two fresh fixtures: first passed, second strict Service control failed with curl 7 after PodIP GET/POST succeeded. EndpointSlice Ready was observed by 15:21:30.645 UTC; native no-endpoints REJECT counters rose for both refused requests before DNAT appeared at 15:21:31.655 and a fresh diagnostic Service request succeeded. Successful markers appear in echo logs; both failed markers are absent. Endpoint/controller/proxy/rule observations, native requests and original source hashes match the published base. Both sampler reaps and UID cleanups confirmed. This establishes asynchronous proxy programming as the producing layer in this reproduction; historical curl 28 remains individually unattributed.

The fixture now requires original Service/Pod EndpointSlice identity/readiness and exact Service response/server-marker coverage from both probes within a separate 30-second pre-policy setup budget. Every setup attempt is retained. Unknown delivery, unexpected output/identities or exhaustion blocks admission. Fresh strict PodIP/Service GET/POST controls and existing denial/rollback criteria are unchanged; diagnostic node rule inspection is absent from qualification code.

Before live diagnosis, 18 offline guards passed. Final source: 30 guards pass (12 new fail-closed cases), all six qualification tests collect without dispatch, compilation/whitespace pass. Pre-review .runs/readiness-network-001/ passed 3 tests in 155.30s, but a review finding then corrected native empty EndpointSlice null ports/endpoints. That earlier pass is retained separately. Final-source .runs/readiness-network-002/ and 003/ passed all three network tests in 156.05s/157.96s, each 151 native receipts, on distinct nodes e0eefa2a-4105-4461-b45d-698a7719cfc1 and 99cfdb34-c33c-47ec-9320-2d3264d76ffa. Four setup observations took 0.326–0.896s; two retained curl 7 refusals before eventual observations and fresh strict controls. Each scenario completed twelve fresh denied markers, positive coverage and rollback. All original fixture UID cleanups and final empty-owned-resource inventories confirmed; source/JUnit/native/marker facts reconciled in .runs/readiness-resume/evidence-audit.json and baseline-audit.json.

All three investigation clusters were removed with original container-ID checks and confirmed absence. Cleanup receipts: .runs/bootstrap/bb046173aa394dbcbe9d86ed3e889064/, 6d8d2ded1d1546ae8e4530b7de1a652d/ and 60db2367caeb4b1895c265fe7f25905d/. Original owner/kubeconfig absent. Unrelated Docker containers remain outside scope. Offline uv dispatch without the repository cache failed before Python/live mutation; explicit existing cache corrected it without dependency changes. Read-only inspection mistakes/corrections remain in .runs/readiness-resume/history.json. No failed attempt was overwritten or counted as a successful control.

## Decisions and next steps

Corsair review's empty-slice finding was corrected before final-source qualification; no unresolved mandatory finding remains. The supported remedy is observed readiness before qualification controls, with native kubectl/curl and no CNI repair or generic fallback. The result does not promise immediate Service routing, diagnose every historical timeout or establish fleet/multi-node reliability. Exact internal controller/proxy event/queue timing remains unknown. OpenShell live slices were not dispatched here; their previously recorded bounded qualification remains separate.

Existing authorization covers tracked publication as a separate draft PR above still-open draft PR #4; do not merge any draft. Never publish run/state/credentials/raw logs. Next bounded component is native 1D policy qualification after scope selection and immutable upstream/source checks. Every new owned node still requires actual storage/kernel/CNI/gateway prerequisites before dependent OpenShell probes. Toolchains, recovery, adapters, PydanticAI and Temporal remain unqualified and later work.

## Continuation prompt

```text
Continue X-McKay/corsair after bounded Service readiness prerequisite qualification.
Read AGENTS.md, README, CURRENT, development/review/handoff skills, HANDOFF-0008,
PLAN-0006, ISSUE-0003 and the focused qualification report. Inspect git/source/
publication and primary upstream inputs; verify actual native receipts, retained
failures/pre-review pass, final-source hashes and immutable cleanup, not handoff
alone. ISSUE-0003 is resolved for fixture admission sequencing; historical curl
28 remains individually unattributed and instantaneous/fleet readiness unclaimed.

Take only the separately scoped native 1D policy slice. Before dependent live
OpenShell work, require exact-node storage/kernel/CNI/gateway controls with pins,
TLS and policy intact. Do not count setup attempts or failed controls as denials;
preserve every attempt and identity-checked cleanup. No toolchain/recovery,
adapter, PydanticAI agent or Temporal integration ahead of its own qualification.
Run the smallest offline guards before live work, review the final diff, update
records/CURRENT, append a handoff and publish only authorized tracked changes.
Never commit .runs/, .state/, credentials or raw logs; do not merge existing drafts.
```
