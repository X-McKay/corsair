---
id: SPEC-0064
kind: spec
title: Reviewed Maven artifact hash lists for the Java toolchain images
status: accepted
updated: 2026-10-13
related: [SPEC-0007, SPEC-0041, SPEC-0045, IDEA-0002, PLAN-0069]
---

# Reviewed Maven artifact hash lists for the Java toolchain images

## Goal and scope

The `java` (JDK 17) and `java8` (JDK 8, SPEC-0045) images fill an offline Maven repository `/opt/corsair-m2` during trusted preparation. Until now that preparation used Maven's strict checksums (`-C`), which only compare each file with the checksum the same repository serves, and wrote `/opt/corsair-m2.sha256` as an inventory of whatever arrived. Nothing pinned the content, unlike the Python images (`--require-hashes` against `wheels.json`). This closes that gap (HANDOFF-0067, IDEA-0002): the image build succeeds only when the cache is exactly a checked-in, reviewed list.

In scope: the image cache (fixture build, Surefire 3.6.0 and its JUnit Platform provider, the fixture's JUnit 4.13.2 or Jupiter 5.14.4 closure, the pinned `maven-dependency-plugin` 3.8.1 `build-classpath` closure, `junit-platform-console-standalone` 1.14.4). Out of scope: a case's own dependencies and its own Surefire providers, which the case setup fetches into a separate case repository (SPEC-0026, `java_image_case setup`); matrix rows.

## Boundaries and design

- `deploy/qualification/toolchains/<dir>/m2.sha256`, one per Java image, in `sha256sum` format: `<sha256>  ./<repository path>`, sorted bytewise. The repository path is the coordinate (`group/artifact/version/file`). Entries cover every cached file except checksum sidecars (`*.sha1`, `*.md5`), the resolver's bookkeeping (`_remote.repositories`, `*.lastUpdated`, `resolver-status.properties`) and its prefix filter under `.meta/`, which are timestamped or served fresh by Central and are not loaded as code.
- Source repository: every artifact must come from Maven Central. Maven 3.10.0 records the origin as `central-8fac3ebd6edbaca3c794783fa38088af0aa128e7`, Central's id plus the SHA-1 of its URL `https://repo.maven.apache.org/maven2`; the build rejects any other origin.
- The Dockerfile has two stages. `cache` is the existing preparation unchanged except for the inventory's scope. The final stage copies `m2.sha256`, runs `diff -u` against the built inventory and the origin check, and fails the build on any changed hash, missing or extra file. The list is copied after the fetch, so a refresh reuses the fetch layer; `/opt/corsair-m2.sha256` in the image equals the list, so the trusted control and the sandbox `sha256sum -c` checks are unchanged.
- Refresh: `make maven-hashes [TOOLCHAINS=<dir>]` builds the `cache` stage with `--no-cache` from the pinned base and writes the list; the reviewer reads the diff (trust on first fetch, then pinned). Every input that decides the set is already pinned: base digest (Maven version and its default plugin versions), fixture POM plugin and dependency versions, dependency plugin and launcher versions.
- Surefire 3.6.0 runs JUnit 4 through its JUnit Platform provider with `junit-vintage-engine` 5.14.4, so the `java8` image holds no `surefire-junit4` provider; a case's own older Surefire fetches its providers in case setup.

## Acceptance and validation

- Two clean `--no-cache` fetches of each image produce the same list; a full build passes with the list; a build with one hash changed and a build with the launcher's entry removed both fail with the `diff` naming the file.
- The fixture runs offline in each new image as the trusted control does (2 tests, 0 failures, 0 skipped).
- Offline guard (`tests/configuration/test_maven_hashes.py`, in `make test-config`): every Java image has a list its Dockerfile checks; lists are well-formed, sorted, unique and free of sidecars; each list holds the fixture POM's pinned plugins and test dependency, the dependency plugin, the launcher (with the same hash as `junit-launcher.sha256`) and the Surefire JUnit Platform provider.
- Live (RIG0, image-only tier): `make toolchain-images TOOLCHAINS="java java8"` builds the files as checked in (the build itself is the check against a clean fetch), the lists equal the `*-maven-cache.sha256` inventories retained from #51's RIG0 builds as sets (checked), and VUL4J-6 through `java_image_case` on the new `java8` image matches #51's result.

## Decisions and open questions

- The check runs after preparation, so a substituted artifact has already executed during the fixture's `mvn test` before the build fails. It cannot reach the image, since the build fails, but it ran in the build container; pinning before execution would need a verifying Maven repository or a pre-fetch by hash, which Maven's resolver does not offer natively. Recorded as a limit, not addressed here.
- `diff` against a plain list, not `sha256sum -c`, because `-c` ignores files that are not listed; the list must also reject extras.
- Not done: the case repository filled during case setup stays checked by Maven's `-C` only; pinning a case's dependencies is a per-case problem, not an image one.
