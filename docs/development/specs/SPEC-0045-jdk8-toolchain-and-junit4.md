---
id: SPEC-0045
kind: spec
title: JDK 8 toolchain image and JUnit 4 runner row
status: draft
updated: 2026-10-13
related: [SPEC-0042, SPEC-0041, SPEC-0039, SPEC-0007, PLAN-0049]
---

# JDK 8 toolchain image and JUnit 4 runner row

## Goal and scope

Al's goal (2026-10-13) is to run every benchmark case end to end, and Corsair must adapt to each case's language, runtime and test-framework version rather than change the project. SPEC-0042's report found that no fetched case runs on the current images; a JDK 8 + Maven row satisfies the runtime of 8 Vul4J cases, and 7 Java cases use JUnit 4. This spec adds that row: one image built on the official Maven + Temurin 8 image, the version-independent JUnit listing of SPEC-0041 inside both Java images, a `junit4` framework for the environment agent and the matrix, and the matrix rows so the SPEC-0042 detector selects the JDK 8 image for JDK 8 projects. Not in scope: TestNG and JUnit 3 runners, JUnit 4 before 4.12, the environment-agent-to-runner command mapping (HANDOFF-0063), OpenShell workspace storage for real repositories (G1/G3), and Java witnesses (G7).

## Boundaries and design

The image `deploy/qualification/toolchains/java8` follows the JDK 17 image exactly: `FROM` the official `maven:3.10.0-eclipse-temurin-8` index digest, trusted preparation with Maven's strict checksums into an offline repository `/opt/corsair-m2` whose file hashes are kept in `/opt/corsair-m2.sha256`, a fixture project in `/opt/corsair-fixture`, user 10001. Both Java images now also prepare the pinned `maven-dependency-plugin` 3.8.1 `build-classpath` closure and `junit-platform-console-standalone` 1.14.4 at `/opt/corsair-junit/` (class file version 52, so it runs on Java 8), with its SHA-256 pinned in `junit-launcher.sha256` and checked during preparation, in the trusted control and in the sandbox. The launcher brings its own Vintage engine, so a project's JUnit 4.12 or 4.13.x is listed unchanged; Vintage refuses JUnit 4 before 4.12, so those projects stay unsupported rather than being upgraded.

The JDK 8 fixture is JUnit 4.13.2 with Surefire 3.6.0 and compiler source/target 1.8; both fixtures carry two methods (`nativeRoundtrip`, `nativeRuntime`, the latter asserting the image's Java feature version) so the runner's two-method listing and execution can run on them. Each image's sources are hashed and invalidated alone (`source_hashes(language)`), so adding an image does not invalidate the others' receipts; `prepare_toolchains --language` prepares one image.

The toolchain gate (SPEC-0007) runs each Java image with the same offline diagnostics (missing artifact through Maven's prefix filter, no discovery, compilation, assertion) using that image's JUnit generation, and additionally runs the Maven runner's own discovery argv (SPEC-0041 listing through the pinned plugin and launcher, offline) and execution argv on the fixture, admitting the listing with `reports/junit_listing.py` and the report with the gate's native report check.

`agents/environment/frameworks.py` admits `junit4` with the same Surefire baseline check as `junit5`; the environment skill names it. The matrix gets the `temurin-8-maven` image row and `junit4`/`junit5` framework rows (scoped with `images:` to the image each was run on) only after the live gate passes, because the detector would otherwise route cases to an unqualified image; until then they are staged in the selection unit test. Framework ranges are an exact union of the versions that ran: JUnit 4 `==4.13.2` on `temurin-8-maven` from the gate, plus `==4.12` only if the real case passes, and JUnit 5 `==5.14.4` on `temurin-17-maven`. The staged rows in the selection test are the template the promoted rows copy.

## Acceptance and validation

Offline: `make test-config`, including the matrix guards (each row is a prepared image with existing evidence), selection of the JDK 8 image for a JDK 8 + JUnit 4.12 POM, JUnit 4.8.2 unsupported, and the `junit4` admission cases. Live on RIG0: both Java images built and loaded on a fresh kind node, the toolchain gate passing for `java8`, `java` and `python`, and the Maven runner (listing and execution) on at least one real JDK 8 + JUnit 4 benchmark case from the PR #42 captures, on the case's unchanged POM. A run outside OpenShell is recorded as image-only, not sandbox qualification.

## Decisions and open questions

One image per runtime version (SPEC-0042), not a JDK 8 toolchain inside the JDK 17 image. Maven 3.10.0 is kept identical across both Java images. The framework rows are language-wide in SPEC-0042's schema although evidence is per image; the notes say which image ran which version. Plan: [PLAN-0049](../plans/PLAN-0049-jdk8-toolchain-and-junit4.md).
