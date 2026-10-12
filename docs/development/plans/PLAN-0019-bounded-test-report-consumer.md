---
id: PLAN-0019
kind: plan
title: Bounded untrusted test report consumer
status: in_progress
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
- [ ] Qualify the fixed inert native producer/consumer on both fresh admitted nodes under the OpenShell agent's exclusive resource ownership.
- [ ] Review results, update report/current/handoff and publish authorized code.

## Validation and progress

Baseline and qualification evidence live privately under `.runs/four-priorities-20261012/root`. Host consumer tests passed26/0.32s, including fresh-process artifact reread. Existing shared dependency consumers passed122/5.37s with one native loop deprecation warning. Native producer case collected1/0.06s after correcting an initial wrong serialized-helper import; both attempts retained. Actual live consumer qualification is pending, on the same two fresh nodes as the independent receipt matrix but with separate case/evidence roots. Published baseline PR17/head01364a1/CI38200340033 verified successful before edits. A preparation read guessed a nonexistent qualification filename; repository search identified the actual existing files, with no mutation or runtime action.

## Decisions and next action

No new artifact store, archive/parser framework, scheduler or security disposition engine. Consume exact stdout artifacts only. Run smallest host tests before any dependent native producer. Do not broaden the claim to executed tests, application conclusions or general file download.
