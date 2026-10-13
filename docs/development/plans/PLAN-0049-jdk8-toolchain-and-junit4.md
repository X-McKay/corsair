---
id: PLAN-0049
kind: plan
title: JDK 8 toolchain image and JUnit 4 runner row
status: in_progress
updated: 2026-10-13
related: [SPEC-0045, SPEC-0042, SPEC-0041, PLAN-0046, PLAN-0045]
---

# JDK 8 toolchain image and JUnit 4 runner row

## Objective and dependencies

Implement [SPEC-0045](../specs/SPEC-0045-jdk8-toolchain-and-junit4.md). Branch `claude/toolchain-jdk8-junit4-x5k2l4` stacks on PR #46 (SPEC-0041 listing) and PR #48 (SPEC-0042 matrix), both merged in. Live steps need RIG0 and the shared kind cluster (one thread at a time).

## Steps

- [x] JDK 8 image source and fixture; launcher and dependency plugin in both Java images; per-image source hashes.
- [x] Gate: JDK 8 sandbox, runner discovery/execution argv in both Java sandboxes.
- [x] `junit4` framework, skill text, matrix rows, offline tests.
- [ ] Build and load images on RIG0; toolchain gate on a fresh node.
- [ ] Maven runner on a real JDK 8 + JUnit 4 case from the #42 captures.
- [ ] Fill measured versions and evidence into the matrix and qualification report; review; handoff.

## Validation and progress

2026-10-13, cloud container (no Docker daemon, no JDK 8): launcher jar SHA-1 matches Maven Central, SHA-256 `7c6968cb…a8bc28`, class file version 52. The JDK 8 fixture's `test-compile`, `build-classpath` and `dependency:copy` steps ran with Maven 3.9.11 on JDK 21, and the launcher listed both fixture methods through the Vintage engine (`2 tests found`). This is not JDK 8 evidence.

## Decisions and next action

Next: RIG0 session; build, load, gate; then the real case.
