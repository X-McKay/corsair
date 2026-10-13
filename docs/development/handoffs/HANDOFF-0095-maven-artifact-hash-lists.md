---
id: HANDOFF-0095
kind: handoff
title: Maven artifact hash lists for the Java images
status: recorded
updated: 2026-10-13
related: [SPEC-0064, PLAN-0069, HANDOFF-0067, IDEA-0002]
---

# Maven artifact hash lists for the Java images

## Verified state

Branch `claude/maven-hash-list-b66ecq` (PR #76), main merged (see git). Delivered under [SPEC-0064](../specs/SPEC-0064-maven-artifact-hash-lists.md):

- `deploy/qualification/toolchains/{java,java8}/m2.sha256`: SHA-256 of every cached artifact by repository path; each Dockerfile's final stage diffs the fresh cache against it and requires Central as every origin. `make maven-hashes [TOOLCHAINS=<dir>]` regenerates a list for review.
- `tests/qualification/image_cases.py`: per-image real cases (`CASES`, VUL4J-6 on `java8`) and per-language harness entries (`LANGUAGES`, Java only), run by hand after `make toolchain-images`. Not in CI: Al deferred real cases in CI until end-to-end runs exist (2026-10-13).
- Offline guards: `tests/configuration/test_maven_hashes.py`, `tests/configuration/test_image_cases.py`.

No matrix row changed. The image gate receipts change with the new source; the next milestone gate covers both Java images.

## Validation and blockers

See [PLAN-0069](../plans/PLAN-0069-maven-artifact-hash-lists.md#validation-and-progress). `make test-config` passed on each pushed head. In the image-only CI job both images built against their lists on every run; while the case step existed, VUL4J-6 discriminated in 2 of 3 runs. No blocker.

## Decisions and next steps

- Real cases leave CI until end-to-end runs exist (Al). When they return: VUL4J-6's PoV still loops about 3.9e9 times on the fix revision, about 5 s of its own 6 s timeout, so a slow runner times out on the fix too; decide then how a fix-side timeout is reported (the thread's proposal: inconclusive, never a pass).
- Node and Ruby add `LANGUAGES` entries and cases when their harnesses land.
- Limit recorded in SPEC-0064: the hash check runs after preparation has executed fetched plugins.

## Continuation prompt

Read SPEC-0064, PLAN-0069 and this handoff. The Java image caches are pinned by checked-in lists; refresh with `make maven-hashes TOOLCHAINS=<dir>` and review the diff. To put real cases back in CI, add a step to `.github/workflows/toolchain-images.yml` that runs `python -m tests.qualification.image_cases <dirs> --evidence .runs/ci/image-cases` with `src` on the path, and settle the VUL4J-6 fix-side timeout first.
