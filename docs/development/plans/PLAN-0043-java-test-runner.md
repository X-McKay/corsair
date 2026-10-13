---
id: PLAN-0043
kind: plan
title: Java test identity, Surefire reports and Maven runner
status: complete
updated: 2026-10-13
related: [SPEC-0039, SPEC-0028, SPEC-0017, SPEC-0033, PLAN-0021, HANDOFF-0061]
---

# Java test identity, Surefire reports and Maven runner

## Objective and dependencies

Implement [SPEC-0039](../specs/SPEC-0039-java-test-runner.md) offline from main `334aa03`: G6 for Java in IDEA-0005 (draft PR #39, not yet on main; no file it changes is touched here). Independent of the kind cluster. The sandbox run of a Java case depends on G1/G3 (storage and fetch-based workspace), G4/G5 (an admitted offline Maven closure in a Java image) and the SPEC-0032 workspace; those stay open.

## Steps

- [x] Generate real Surefire reports: the Java toolchain POM (Surefire 3.6.0, JUnit 5.14.4) over a small sample project; JSPWiki at the baseline `f140a2a4` and candidate `88d89d65` with the frozen benchmark test, on the upstream POM (Surefire 2.22.0, JUnit 5.4.0) and with the framework versions overridden to the image's.
- [x] `JavaTestId` and `#` in SPEC-0017 claim ids; `reports/surefire.py` with the shared `admit_xml` from `reports/junit.py`.
- [x] `adapters/native_runner.py` from the pytest runner's orchestration (behaviour unchanged, existing tests pass), then `adapters/maven_runner.py` with dry-run discovery.
- [x] Offline tests over the real reports and fake ports; local host runs of the runner through real Maven.
- [x] Witness requirements recorded in SPEC-0039; nothing built.
- [x] Review, records, `CURRENT.md`, handoff.

## Validation and progress

All runs on 2026-10-13 in the cloud development container: OpenJDK 21.0.12, Maven 3.9.11, host processes, no sandbox. None of this is qualification.

- Toolchain sample: `mvn -B -ntp -Dmaven.repo.local=… test` on `deploy/qualification/toolchains/java` passed 1/1 (closure 14 MB after the sample project's runs).
- JSPWiki, upstream POM, `-pl jspwiki-main -am -Dsurefire.failIfNoSpecifiedTests=false -Dtest=<class>#<m1>+<m2> test`: baseline exit 1, control passed, security failed at `BenchmarkWikiServletForwardingTest.java:63` with forward URL `//templates/210/images/SilkIconSet-readme.txt?page=…`; candidate exit 0, both passed. These match the README's evaluator hypotheses; they are the first executions of the draft, on the host with JDK 21 rather than an admitted Java 8–17 environment, and the build took 3.5–28.6 s including dependency downloads.
- Dry run on the upstream POM: JUnit 5.4.0 ignored `-Djunit.platform.execution.dryRun.enabled=true` and ran both bodies (exit 1, security failed). With `-Djunit.version=5.14.4` only (Surefire 2.22.0): `Tests run: 0`, exit 0. With `-Djunit.version=5.14.4 -Dplugin.surefire.version=3.6.0`: both reported skipped with the dry-run message, exit 0.
- `MavenRunner` through a scratch local subprocess executor and `LocalArtifacts`, Maven offline (`-o`): sample project discovered then baseline-shaped outcome (control passed, security failed at line 21); two-module sample (`app` depends on `lib`) the same with `-pl app -am`; JSPWiki upstream POM refused at discovery on both commits (`Dry run not honoured …; test bodies may have run`), nothing executed; JSPWiki with the two overrides discovered both ids, baseline control passed and security failed at line 63, candidate both passed. The combined JSPWiki Maven closure for both framework versions was 56 MB (186 jars). The scratch driver and trees were not committed.
- `make test-config`: 918 passed (853 on main plus 65 new), one pre-existing collection warning. Codex review on PR #41 found that the gate `TestId` still refused `#`, so a Java run failed in `run_evidence`; reproduced by a new test (failed before, passes after the pattern fix); 919 passed.

Unrun: any OpenShell execution; Temporal checks (no workflow changed); the Java toolchain image gate (image unchanged).

## Decisions and next action

Decisions are in SPEC-0039. Admitting the JSPWiki framework override (JUnit 5.14.4 and Surefire 3.6.0, as in the qualified image) is an operator decision recorded as open, together with a Java image carrying JSPWiki's offline closure. Next bounded action, after G1/G3: run `MavenRunner` inside the SPEC-0032 test workspace on a fresh node with that closure, three runs per revision, then wire Java ids through planning and authoring (G8). Stop if the dry run is not honoured in the image or the closure cannot be admitted offline.
