---
id: PLAN-0019
kind: plan
title: Bounded untrusted test report consumer
status: complete
updated: 2026-10-12
related: [SPEC-0017]
---

# Bounded untrusted test report consumer

## Objective and dependencies

Implement [SPEC-0017](../specs/SPEC-0017-bounded-test-report-consumer.md) using the existing artifact/execution ports. Root owns this component and shared pins/publication while Sol agents own native durable composition, local model qualification and fresh-process OpenShell receipt evidence.

## Steps

- [x] Inspect source/contracts and define one bounded report schema with explicit trust limits.
- [x] Implement narrow immutable report contracts/consumer and meaningful negative checks.
- [x] Verify fresh-process actual artifact reread using actual LocalArtifacts and simulated host receipts.
- [x] Qualify the fixed inert native producer/consumer on both fresh admitted nodes under the OpenShell agent's exclusive resource ownership.
- [x] Review results, update report/current/handoff and publish authorized code.

## Validation and progress

Baseline and qualification evidence live privately under `.runs/four-priorities-20261012/root`. Host consumer tests passed26/0.32s, including fresh-process artifact reread. Existing shared dependency consumers passed122/5.37s with one native loop deprecation warning. Native producer case collected1/0.06s after correcting an initial wrong serialized-helper import; both attempts retained. Actual live consumer qualification passed on the same two fresh nodes as the independent receipt matrix, with separate case/evidence roots. Published baseline PR17/head01364a1/CI38200340033 verified successful before edits. A preparation read guessed a nonexistent qualification filename; repository search identified the actual existing files, with no mutation or runtime action.

## Decisions and next action

First native node: report-003 passed one case in 98.48s, exercising exact native exits 0/1 and two 377-byte reports. Root independently checked stdout digests/claims/operation/source/test bindings, original sandbox cleanup and absent worker PIDs. Earlier report launch attempts are retained: report-001 failed before pytest because the launcher omitted the repository UV cache; report-002 completed only read-only prerequisite queries before failing missing gateway fixture registration. The explicit gateway fixture import corrected discovery; no application operation was replayed. Complete runtime source-v3 retains 77 inputs, with the fixture import as the sole change from receipt node001's preserved v2 freeze. Second fresh node passed one report case/94.93s with the same corrected v3 inputs. Both original cluster IDs, gateways, tasks, workers, private directories, forwards and volumes were confirmed absent. Root independently audited actual receipts, stdout/artifact bindings, JUnit and exact-container cleanup for both nodes.

No new artifact store, archive/parser framework, scheduler or security disposition engine. Consume exact stdout artifacts only. Run smallest host tests before any dependent native producer. Do not broaden the claim to executed tests, application conclusions or general file download.

Final review found shared-marker evidence-root overlap risk; removed only the report marker/unused import after all live freezes and cleanup. Existing execution_artifacts selection and explicit report selection each collect one intended case (0.06s each). Added five existing offline Temporal guards to Make after live work. These selector changes do not alter qualified runtime logic. Root final two-node audit is retained privately; publication remains authorized through draft PR18.
