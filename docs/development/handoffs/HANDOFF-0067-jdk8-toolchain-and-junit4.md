---
id: HANDOFF-0067
kind: handoff
title: JDK 8 toolchain image and JUnit 4 qualified
status: recorded
updated: 2026-10-13
related: [SPEC-0045, PLAN-0049, SPEC-0042, SPEC-0041, SPEC-0046]
---

# JDK 8 toolchain image and JUnit 4 qualified

## Verified state

Branch `claude/toolchain-jdk8-junit4-x5k2l4` (PR #51), with main merged through 759b016 (#48, #53, #55 and others). Delivered:
- The `java8` image (official `maven:3.10.0-eclipse-temurin-8` by index digest).
- The pinned JUnit Platform console launcher 1.14.4 and maven-dependency-plugin 3.8.1 in both Java images.
- Per-image source hashes and `--language` preparation.
- One gate per image (`test_native_<dir>_toolchain`), sharing one module-scoped gateway and writing evidence per test.
- The `junit4` framework in the environment agent and skill.
- The image-only harness `tests/qualification/java_image_case.py`.
- A Makefile pytest root pin (`-c`/`--rootdir` for this checkout).
- Matrix rows `temurin-8-maven` (runtime 8.0.504), `junit4` `==4.13.2 || ==4.12` on it, and `junit5` `==5.14.4` on `temurin-17-maven`.

Remaining limits:
- JUnit 4 before 4.12 is unsupported (no Vintage discovery).
- JUnit 4.12 rests on one image-only real case (VUL4J-6), not on a sandbox run.
- Neither Java image has a checked-in expected Maven cache manifest.
- The SPEC-0042 benchmark report has not been regenerated against the new matrix.

## Validation and blockers

Offline: `make test-config` passes on this head (the count is in the PR). RIG0 live work is recorded in [PLAN-0049](../plans/PLAN-0049-jdk8-toolchain-and-junit4.md) and the [toolchain report](../../qualification/openshell-toolchains.md#spec-0045-jdk-8-image-and-per-image-gates-2026-10-13):
- Fresh cluster owned by the worktree, after `make kind-down` of the previous cluster from corsair-live-e2e.
- Admission: 1 passed, 89 s.
- Network: 3 passed, 169 s.
- Final gate at 3ad3755: 3 passed in 454 s, with all cleanup confirmed.
- VUL4J-6 at 6945e74:
  - Fix revision: control and PoV passed.
  - Vulnerable revision: control passed; the PoV hit its own 6 s timeout, which is the CVE-2018-1324 loop.

Failed attempts are retained, each a single diagnosed attempt:
- The first VUL4J-6 setup had no Surefire 2.19.1 provider.
- Two VUL4J-6 runs failed on the missing artifact-store root.
- Admission collection loaded the main checkout's code because of the pytest root inference.
- The gateway install refused evidence kept outside the running checkout's `.runs`.
- The java and python gates errored when the per-test gateway was consumed by the first test.

The gate evidence predates the #55 merge, which added the CPython 3.7 gate to the same harness without changing the Java or 3.12 paths. Evidence lives under the worktree's `.runs/jdk8-toolchain-20261013/`, with logs and a `SUMMARY.md` under `/home/al/git/corsair/.runs/jdk8-toolchain-20261013/`. Archive the worktree's evidence before deleting the worktree. The cluster was handed to the CPython 3.7 thread by cross-session message; it is still owned by this worktree until that thread runs `make kind-down` here.

## Decisions and next steps

Decisions:
- The control for a replayed third-party PoV is a Corsair-authored verbatim copy of an unrelated upstream test (option A), and the PoV stays byte-identical.
- Qualification evidence lives in the running checkout's own `.runs`; the provenance check is unchanged.
- The expected Maven cache manifest is a follow-up for both Java images, because adding it changes their gate receipts.

Follow-ups in other threads:
- "Maven artifact hash list".
- "Live qualification tooling": a one-command chain, cluster status and archiving, allow rules, offline harness stubs, and the standing decisions.

Next: Al's "merge" once CI is green. After it merges, regenerate SPEC-0042's report against the new matrix and check VUL4J-6's recorded Maven 3.5.0 and JDK 9 needs.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then SPEC-0045, PLAN-0049 and HANDOFF-0067. Verify PR #51's merge state on GitHub and the matrix rows against the toolchain report. If merged, regenerate benchmarks/runtime-requirements.{md,json} with evals/benchmark/runtimes.py against the current matrix (checkout and parent POMs need network; Jenkins parents come from RIG0), and investigate why VUL4J-6 is recorded as needing Maven 3.5.0 and JDK 9 although it ran on the JDK 8 image. Run make test-config, update records and CURRENT.md, and write a new handoff.
```
