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
- [x] `junit4` framework, skill text, offline tests; matrix rows staged in the selection test, held out of the matrix until the gate passes.
- [ ] Build and load images on RIG0; toolchain gate on a fresh node (java8 passed at 3cb0bc6; all three rerun on final source pending).
- [x] Maven runner on a real JDK 8 + JUnit 4 case from the #42 captures (VUL4J-6, image-only).
- [ ] Fill measured versions and evidence into the matrix and qualification report; review; handoff.

## Validation and progress

2026-10-13, cloud container (no Docker daemon, no JDK 8): launcher jar SHA-1 matches Maven Central, SHA-256 `7c6968cb…a8bc28`, class file version 52. The JDK 8 fixture's `test-compile`, `build-classpath` and `dependency:copy` steps ran with Maven 3.9.11 on JDK 21, and the launcher listed both fixture methods through the Vintage engine (`2 tests found`). This is not JDK 8 evidence.

2026-10-13, RIG0, worktree `.worktrees/claude-toolchain-jdk8-junit4-x5k2l4` at ed57d13: `prepare_toolchains build` once per image, all controls passed. java8 `corsair-java8:81777d352ab28226` config `sha256:b48b9086…`, Temurin 1.8.0_504-b01, Maven 3.10.0; java `corsair-java:c7e6b24f0068035d` config `sha256:e23aaf05…`; python `corsair-python:61a3e8db1afb1726` config `sha256:68f08d0e…`. VUL4J-6: the fix commit adds no test; the PoV is Vul4J's `Test_CVE_2018_1324` (branch VUL4J-6 head 45ddad15), single method. First setup (ed57d13) cached no Surefire 2.19.1 JUnit provider, because Surefire resolves it only when a test runs; setup now fetches the project's own providers without running a body and fails if none resolves (acc1844).

Gate convention (#53): one test per image, `test_native_<dir>_toolchain` with `@pytest.mark.toolchain('<dir>')`; each writes under `<CORSAIR_QUAL_RUN>/<test name>/` (an `image_kube` view); one module-scoped gateway serves every selected image, its receipts at the run's top level. Select one image by node id (or #55's `TOOLCHAINS=` once merged), never `-k`.

2026-10-13, RIG0, fresh cluster owned by the worktree (node container dd6cd613…; the previous cluster deleted by `make kind-down` from corsair-live-e2e against its owner receipt). Qualification runs under the worktree's `.runs/jdk8-toolchain-20261013/` (the gateway installer and network check accept evidence only from the running checkout's `.runs`); logs and VUL4J-6 evidence under `/home/al/git/corsair/.runs/jdk8-toolchain-20261013/` with `SUMMARY.md`. One attempt per step:
- `qualify-admission` with the evidence dir in the main checkout's `.runs`: failed at collection, no test ran. pytest takes the evidence path as a positional path before the conftest registers `--evidence-dir`, so the common ancestor was the main checkout and it loaded that checkout's pyproject and older src (ModuleNotFoundError). Retained as `qual-admission`; the Makefile now passes `-c $(CURDIR)/pyproject.toml --rootdir=$(CURDIR)` to every pytest call (reproduced and fixed offline with an ancestor `pyproject.toml`).
- `qualify-admission` (`PYTEST_ADDOPTS` root override) into the main `.runs`: 1 passed, 103.5 s; then `openshell-install` refused it as not host-owned (`install_gateway.py`, before any helm call). Retained.
- At 3cb0bc6 in the worktree's `.runs`: `qualify-admission` 1 passed, 89 s; `openshell-install` ok (20 s); `qualify-network` 3 passed, 169 s; `toolchain-images-load` loaded java, java8, python.
- `qualify-toolchain` at 3cb0bc6: `test_native_java8_toolchain` passed, 200 s (config `sha256:b48b9086…`, javac 1.8.0_504, Maven 3.10.0, runner listed both `corsair.NativeTest` methods through junit-vintage, missing-artifact/no-discovery/compilation/assertion diagnostics, sandbox, PV and gateway cleanup confirmed). `test_native_java_toolchain` and `test_native_python_toolchain` errored in setup: the per-test gateway fixture's teardown uninstalls the gateway, so only the first gate had one. Fixed with the module-scoped gateway above (verified offline with a stubbed gateway: one install, three gates, separate evidence). The java8 pass does not count as final: its source hashes predate the fix.
- VUL4J-6 (image-only, `java_image_case`, java8 image, setup2's case repository, JUnit 4.12 and Surefire 2.19.1 from the project's own POM): the first runs crashed in the harness before any command (artifact root not created; fixed 6945e74). At 6945e74: fix commit ebd7ff28 (overlay with the verbatim-copied control `testBenignZipShortToBytes`, PoV byte-identical to Vul4J 45ddad15; overlay sha256 18a406a5…, source ZipShortTest sha256 27a06a0c…, Vul4J original 5d597bb3…): both ids discovered, control passed, PoV passed, 8.8 s. Vulnerable ef60e0da with the fix's test file (patch sha256 830cd36b…): control passed, PoV error `TestTimedOutException` after 6000 ms (the CVE-2018-1324 loop hitting the test's own timeout), 11.8 s. Container cleanup confirmed for both.

## Decisions and next action

Next: rerun `openshell-install` and one `make qualify-toolchain` (all three images) on the final source; then add the `temurin-8-maven` row, `junit4` `==4.13.2 || ==4.12` (4.13.2 from the gate fixture in the sandbox, 4.12 from VUL4J-6 image-only) on that image, and `junit5` `==5.14.4` on `temurin-17-maven` if the java gate passes; report; handoff. Expected Maven cache manifest (base-image skill rule) for both Java images: follow-up PR, because adding it changes the image sources and their gate receipts.
