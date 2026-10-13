# Real Surefire reports

Offline fixtures for [SPEC-0039](../../../docs/development/specs/SPEC-0039-java-test-runner.md). Each XML file is a `TEST-<class>.xml` written by Maven Surefire on 2026-10-13 in a development container (OpenJDK 21.0.12, Maven 3.9.11), on the host and not in a sandbox. The only change is that every `<property>` line inside the suite's `<properties>` was deleted, because those lines carried host paths and proxy settings; the empty element is kept. Nothing here is qualification evidence.

| File | Source | Surefire / JUnit | Command (`mvn -B -ntp -Dmaven.repo.local=…` plus) |
| --- | --- | --- | --- |
| `sample-documents.xml` | [`sample-project/`](sample-project) with the [Java toolchain POM](../../../deploy/qualification/toolchains/java/pom.xml) | 3.6.0 / 5.14.4 | `test -Dtest='corsair.sample.DocumentsTest#readsOrdinaryDocument+refusesTraversalOutsideRoot'` |
| `sample-documents-dry-run.xml` | same | 3.6.0 / 5.14.4 | the same plus `-Djunit.platform.execution.dryRun.enabled=true` |
| `sample-broken.xml` | same | 3.6.0 / 5.14.4 | `test -Dtest='corsair.sample.BrokenTest#setupErrors+skippedTest'` |
| `jspwiki-baseline.xml` | JSPWiki `f140a2a4…` plus the frozen [benchmark test](../../../benchmarks/cases/jspwiki-forwarding/BenchmarkWikiServletForwardingTest.java) | 2.22.0 / 5.4.0 (upstream POM) | `-pl jspwiki-main -am -Dsurefire.failIfNoSpecifiedTests=false -Dtest='org.apache.wiki.BenchmarkWikiServletForwardingTest#benignPageKeepsEncodedPageParameter+inertWebRootResourceCannotSelectForwardTarget' test` |
| `jspwiki-candidate.xml` | JSPWiki `88d89d65…` plus the same test | 2.22.0 / 5.4.0 | same |
| `jspwiki-baseline-dry-run-ignored.xml` | baseline | 2.22.0 / 5.4.0 | same plus the dry-run property, which JUnit 5.4 ignores: the bodies ran |
| `jspwiki-baseline-surefire3.xml` | baseline | 3.6.0 / 5.14.4 | same plus `-Djunit.version=5.14.4 -Dplugin.surefire.version=3.6.0` |
| `jspwiki-candidate-surefire3.xml` | candidate | 3.6.0 / 5.14.4 | same |
| `jspwiki-baseline-dry-run-surefire3.xml` | baseline | 3.6.0 / 5.14.4 | same plus the dry-run property, honoured |

The JSPWiki test file's SHA256 was `6ebf62443a54fc98b0d3f3680d4aa0fde239888db10bc8b5158026faa369b95d` in both trees, at `jspwiki-main/src/test/java/org/apache/wiki/`. The JSPWiki trees were shallow fetches of the exact commits from github.com.
