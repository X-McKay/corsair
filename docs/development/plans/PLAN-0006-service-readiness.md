---
id: PLAN-0006
kind: plan
title: Diagnose and qualify initial Service readiness
status: complete
updated: 2026-10-11
related: [ISSUE-0003, SPEC-0001, PLAN-0005, HANDOFF-0007]
---

# Diagnose and qualify initial Service readiness

## Objective and dependencies

Resolve ISSUE-0003 within the ordinary-pod fixture boundary. Base cc97b88204b92fd7e9e8621a34d9abeeba9da08c matched the published open draft PR #4; clean resume. Read actual failing native curl receipts and all six failed-fixture UID cleanup receipts, not just handoff. Prior three diagnostic fixtures did not reproduce. No owned cluster/state survives; unrelated Docker containers are outside scope. Keep runtime lock, CNI, workload probes, policy, timeouts and denial criteria unchanged. No OpenShell deployment, adapter, agent or Temporal work.

## Steps

- [x] Capture original startup behavior with native EndpointSlice/controller/proxy/rule observations on a fresh owned cluster; establish the producing layer or retain an unresolved diagnosis.
- [x] Implement only the evidenced supported fixture prerequisite and meaningful offline failure guards.
- [x] Requalify initial real controls, policy denials/rollback and UID cleanup on two fresh clusters; retain every diagnostic/failed attempt.
- [x] Review the diff, update issue/report/runbook/current work and append a handoff; prepare only tracked authorized changes for publication.

## Validation and progress

Before live work: UV_OFFLINE=true make test-config: 18 passed in 0.07s. Published branch SHA verified with git ls-remote and gh pr view. Existing failed Service controls follow successful PodIP controls and precede their policies; curl exits 7/28 are retained. Fixture already has a real HTTP readiness probe; At resume, Pod Ready alone was the sole fixture setup readiness prerequisite. Read-only inspection attempted an absent configuration-test filename; corrected by rg --files. Initial release inspection output was truncated; compact primary metadata and source bytes were then retained.

## Decisions and next action

Capture native observations before choosing any correction. Kubernetes documents separate EndpointSlice publication and kube-proxy rule synchronization; actual failure-time evidence is required for attribution. Do not introduce blind sleeps, policy weakening or retry failed controls into a claimed pass. Prerequisite observations, if supported by evidence, must retain bounded failures and require fresh successful controls before any policy mutation. Unknown native delivery stops dependent work; all fixture/cluster cleanup compares immutable identities.

Native baseline .runs/readiness-baseline-001/ reproduced curl 7 on fixture 2 after PodIP GET/POST passed. EndpointSlice was Ready by 15:21:30.645 UTC; requests at 15:21:31.217/31.406 were refused while native proxy REJECT counters rose 0→1→2. DNAT appeared by 31.655; a fresh diagnostic request at 31.768 passed. Both namespaces UID cleanup and sampler reap confirmed. Selected immutable Kubernetes proxy source implements exactly the observed no-endpoints rejection; native config minSyncPeriod 1s. This establishes asynchronous proxy programming as the producing layer in this reproduction; historical curl 28 remains individually unattributed.

Implemented a fixture-only 30-second EndpointSlice identity/readiness plus exact Service GET/log prerequisite from both probes using native kubectl/curl. Attempts/commands and readiness=false on failure remain attributable; fresh strict GET/POST PodIP/Service controls and all policy convergence/deny criteria are unchanged. No privileged inspection is used by the corrected qualification fixture. UV_OFFLINE=true make test-config: 28 passed in 0.09s before live requalification. Ten new guards reject stale endpoints, wrong output/exec errors, unknown delivery, persistent connection failure and relaxed fresh controls. Dispatch-cache failure and read-only inspection corrections retained in .runs/readiness-resume/history.json.

First corrected complete suite .runs/readiness-network-001/ passed 3 tests in 155.30s, retained a setup curl 7 followed by both successful observations and fresh strict controls; both fixture UID cleanups and final inventory passed. Cluster bb046173... cleanup confirmed original container 3aef1990... absent. During source/evidence review, native empty EndpointSlice was observed with null ports/endpoints. Corrected the prerequisite to wait for endpoints before validating their port and extended the empty-slice guard. First suite remains a retained pre-review pass; qualify final source on two subsequent fresh clusters rather than counting it as final-source evidence. Added existing-policy and missing-server-log guards; 30 offline checks pass in 0.10s.

Final-source .runs/readiness-network-002/ passed 3 tests in 156.05s (151 native receipts) on node e0eefa2a-4105-4461-b45d-698a7719cfc1. Both setup/strict control/policy/rollback scenarios and UID cleanups passed, one setup curl 7 retained. Final fixture/PVC/PV inventory empty. Cluster .runs/bootstrap/6d8d2ded1d1546ae8e4530b7de1a652d/cleanup.json confirmed original container f4ac797e... absent. Pre/post source hashes, successful exact native requests and 12 denied markers per scenario reconciled in .runs/readiness-resume/evidence-audit.json. Six live tests collect without dispatch, Python compilation and whitespace pass. At that checkpoint the last fresh-cluster repeat was underway; implementation remained frozen.

Final review against the Corsair review skill: native operator kubectl/curl observations are limited to the trusted fixture, do not alter policies or operator pins, and provide no application adapter/fallback. Empty native EndpointSlice handling finding corrected before the two final-source runs. Existing strict controls/denials and cleanup source remain unchanged. Native shared get/request helpers gain optional bounded timeouts with original defaults preserved; other live OpenShell slices were not rerun because this scope changes only fixture Service setup. Source/evidence and offline failure guards reviewed; no further mandatory code finding. At that checkpoint the second final-source repeat and its cleanup/record completion were outstanding; completion is recorded below. Tracked publication follows the final review.

Final-source .runs/readiness-network-003/ passed 3 tests in 157.96s (151 native commands) on node 99cfdb34-c33c-47ec-9320-2d3264d76ffa. Both fixture UID cleanups and final empty-owned-resource inventory passed. Cluster .runs/bootstrap/60db2367caeb4b1895c265fe7f25905d/cleanup.json confirmed container 60a6f100... absent. Owner/kubeconfig absent; unrelated Docker containers preserved. Final-source 002/003 qualify the bounded correction; all baseline/pre-review/setup failures remain retained. Evidence audits reconcile actual native receipts/JUnit/source hashes/marker and cleanup facts. ISSUE-0003 is resolved for fixture control admission, with historical curl 28 individually unattributed. The focused qualification report and HANDOFF-0008 preserve the limits.

Existing user authorization covers tracked publication on codex/service-readiness, stacked above open draft PR #4 without merging any draft. Resolve the published revision through git log for HANDOFF-0008; no future SHA is assumed. Next work is a separately bounded native 1D policy slice after exact-node mandatory gates; this investigation does not dispatch it.
