# Real Surefire reports

Offline fixtures for [SPEC-0039](../../../docs/development/specs/SPEC-0039-java-test-runner.md) and [SPEC-0041](../../../docs/development/specs/SPEC-0041-version-independent-junit-discovery.md). Each XML file is a `TEST-<class>.xml` written by Maven Surefire on 2026-10-13 in a development container (OpenJDK 21.0.12, Maven 3.9.11), on the host and not in a sandbox. The only change is that every `<property>` line inside the suite's `<properties>` was deleted, because those lines carried host paths and proxy settings; the empty element is kept. Nothing here is qualification evidence.

| File | Source | Surefire / JUnit | Command (`mvn -B -ntp -Dmaven.repo.local=…` plus) |
| --- | --- | --- | --- |
| `sample-documents.xml` | [`sample-project/`](sample-project) with the [Java toolchain POM](../../../deploy/qualification/toolchains/java/pom.xml) | 3.6.0 / 5.14.4 | `test -Dtest='corsair.sample.DocumentsTest#readsOrdinaryDocument+refusesTraversalOutsideRoot'` |
| `sample-broken.xml` | same | 3.6.0 / 5.14.4 | `test -Dtest='corsair.sample.BrokenTest#setupErrors+skippedTest'` |
| `jspwiki-baseline.xml` | JSPWiki `f140a2a4…` plus the frozen [benchmark test](../../../benchmarks/cases/jspwiki-forwarding/BenchmarkWikiServletForwardingTest.java) | 2.22.0 / 5.4.0 (upstream POM) | `-pl jspwiki-main -am -Dsurefire.failIfNoSpecifiedTests=false -Dtest='org.apache.wiki.BenchmarkWikiServletForwardingTest#benignPageKeepsEncodedPageParameter+inertWebRootResourceCannotSelectForwardTarget' test` |
| `jspwiki-candidate.xml` | JSPWiki `88d89d65…` plus the same test | 2.22.0 / 5.4.0 | same |
| `jspwiki-baseline-surefire3.xml` | baseline | 3.6.0 / 5.14.4 | same plus `-Djunit.version=5.14.4 -Dplugin.surefire.version=3.6.0` |
| `jspwiki-candidate-surefire3.xml` | candidate | 3.6.0 / 5.14.4 | same |
| `junit4-legacy.xml` | [`junit4-project/`](junit4-project) | 2.22.0 / JUnit 4.12 | `test -Dtest='corsair.sample.LegacyTest#control+security'` |

The JSPWiki test file's SHA256 was `6ebf62443a54fc98b0d3f3680d4aa0fde239888db10bc8b5158026faa369b95d` in both trees, at `jspwiki-main/src/test/java/org/apache/wiki/`. The JSPWiki trees were shallow fetches of the exact commits from github.com.

The two `listing-*.txt` files are the stdout of the JUnit Platform console launcher 1.14.4 (`junit-platform-console-standalone`, from Maven Central) run as `java -jar <launcher> discover --disable-banner --disable-ansi-colors --details=flat --class-path <test-classes>:<classes>:<test classpath> --select-method=<class>#<m1> --select-method=<class>#<m2>`, where the test classpath was written by `test-compile org.apache.maven.plugins:maven-dependency-plugin:3.8.1:build-classpath -Dmdep.includeScope=test` on the unchanged project POM: `listing-jspwiki.txt` against JSPWiki `f140a2a4…` (JUnit 5.4.0), `listing-junit4.txt` against `junit4-project/` (JUnit 4.12). Neither listing ran a test body. They contain no host paths and are unmodified.
