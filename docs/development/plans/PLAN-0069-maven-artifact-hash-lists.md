---
id: PLAN-0069
kind: plan
title: Maven artifact hash lists for the Java toolchain images
status: in_progress
updated: 2026-10-13
related: [SPEC-0064, PLAN-0049, HANDOFF-0067]
---

# Maven artifact hash lists for the Java toolchain images

## Objective and dependencies

Implement SPEC-0064 for the `java` and `java8` images. Based on main after PR #51 merged (93a0fab), which carries both images and their gates. No matrix row changes.

## Steps

- [x] Two-stage Dockerfiles: unchanged preparation, then `diff` against the checked-in `m2.sha256` and the Central origin check.
- [x] Generate both lists from clean fetches; `make maven-hashes` to refresh.
- [x] Offline guard in `make test-config`; base-image skill rule updated.
- [x] Compare with #51's retained RIG0 inventories (same artifacts and hashes).
- [ ] RIG0 image-only run: build both images from the checked-in files, VUL4J-6 on `java8`.

## Validation and progress

2026-10-13, cloud container, Docker 29.8.2. The container reaches Maven Central only through the session's TLS-re-terminating proxy on the host loopback, so each build here used a scratch copy of the Dockerfile with two lines after the first `FROM` (the proxy CA truststore and JVM proxy options) and `--network=host`; Maven commands and checks are as checked in. Maven's `-C` verified Central's SHA-1 for every file, so the re-terminated TLS did not change content unchecked.
- `java` (Maven 3.10.0, JDK 17 base digest `5394efaa…`): 294 entries; `java8` (Maven 3.10.0, Temurin 8 base digest `f2cb5273…`): 293 entries (89 JARs, 204 POMs). All 294/293 `_remote.repositories` origins are `central-8fac3ebd…`.
- Second `--no-cache` build of each full image (fresh fetch, then the final-stage check): passed, so the lists reproduce.
- Negative: `java8` with the first hash altered failed (`diff` showed the json-simple 3.0.2 line); with the launcher entry removed failed (`diff` showed the extra file). The origin filter was checked on synthetic input (a `>evil=` line is reported).
- Fixture control on both new images (`--network=none`, UID 10001, `sha256sum -c` of the launcher and the cache, `mvn -o test`): 2 tests, 0 failures, 0 errors, 0 skipped, `nativeRoundtrip` and `nativeRuntime`.
- Comparison with RIG0 (read through the linked device folder, no command run there): #51's retained inventories from its RIG0 builds, fetched from Central directly with no proxy (`.worktrees/claude-toolchain-jdk8-junit4-x5k2l4/.runs/toolchains-image/ecbaf3a0…/java8-maven-cache.sha256` and `f2ddf997…/java-maven-cache.sha256`), hold exactly the same 293 and 294 path and hash pairs as the lists. Only their order differs: the old inventory was sorted in the image's locale, and the build now sorts with `LC_ALL=C` for both the list and the check.
- `make maven-hashes` itself was not run here (it needs direct access to Central); its commands were run through the proxy copy above.
- Not run here: VUL4J-6. The image-case harness's setup phase needs Central from a bridge-network container; running it on the host network to reach the proxy was refused by this session's safety check. It goes to RIG0 with the image build.

## Decisions and next action

Next: the RIG0 paste in the PR (worktree `/home/al/git/corsair/.worktrees/claude/maven-hash-list-b66ecq`): `make toolchain-images TOOLCHAINS="java java8"`, then VUL4J-6 image-only on the new `java8` config. The images' gate receipts change with this source, so #51's live gate evidence names the old source; per the process rule this toolchain-only change needs the image-only tier, not a new kind gate.
