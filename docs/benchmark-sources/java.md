# Java benchmark sources for Corsair

**Author:** Manus AI  
**Catalog:** `benchmarks/catalog/java.json` (178 candidate records)

The catalog contains **120 source-backed CWE-Bench-Java CVE records**, **42 VJBench CVE records**, and **16 project-only framework candidates**. Every entry has `validation_status: "candidate"`. This is an external-realism acquisition backlog, not an executed Corsair benchmark: no entry is claimed runnable, vulnerable, exploitable, fixed, or differentially verified by Corsair.

## Concrete real-world case inventories

[CWE-Bench-Java] documents **120 CVEs** across path traversal, OS-command injection, cross-site scripting, and code injection. Its inventory includes repository URLs, version tags, buggy commits, fixed commits, and advisory IDs. The catalog imports all 120 rows as IDs beginning `CWE-Bench-Java:` and links each to the source-listed buggy revision. Building or replaying any entry remains a separate controlled verification task. [1] [2]

[VJBench] adds **42** named Java vulnerability records across web, networking, template, data-binding, XML, and serialization-adjacent projects. Its inventory records project URL, CVE, CWE, human-patch URL, and NVD URL. The catalog imports all 42 as `VJBench:` records and links them to their declared human patches. VJBench calls these records reproducible, but that source label is not local Corsair validation. [3]

[Vul4J] is the strongest next-stage reproduction source. Its current documentation reports **129 entries**: 79 PoV-based and 50 SpotBugs-only entries. It publishes human patches and execution metadata with a Docker-oriented workflow. It remains a source backlog rather than a duplicate candidate list because the imported inventories already provide 162 concrete case records. Source-level reproduction statements do not establish Corsair results. [4]

[VCC-Eval] adds provenance for future acquisition: its manually curated records relate CVEs and CWEs to introducing and fixing commits and affected lines. It is a candidate generator rather than a current-build claim. [5]

## Controlled synthetic coverage

[OWASP Benchmark for Java] is a runnable AST benchmark. Its expected-results manifest has **2740** rows with test name, category, true/false vulnerability label, and CWE. Use it for positive/negative scoring and request-flow coverage while retaining its deliberately constructed nature. [6] [7]

[NIST SARD Juliet Java 1.0] supplies **14,184** Java tests across **106 CWEs** and is public domain. It is a broad deterministic language control corpus, not a real-CVE corpus. [8]

## Framework and runtime breadth

Clearly marked **project candidates**, not alleged vulnerability cases, cover Spring Boot/Petclinic, Quarkus, Micronaut, Dropwizard, Javalin, Eclipse Vert.x, Helidon, Play, Apache Camel, Keycloak, Jenkins, gRPC Java, Apache Kafka, Eclipse Jetty, Vaadin Flow, and WebGoat. WebGoat is a deliberately insecure Java security-learning application; its own documentation warns it should stay locally bound or otherwise isolated. [9]

Preserve each source’s historical Java/Maven/Gradle requirements rather than normalizing every project to one JDK. CWE-Bench-Java specifically anticipates JDK 7, 8, and 17 plus Maven/Gradle combinations. [1] Pin the source revision, resolve dependencies in a disposable environment, capture the actual build command, and only then add an independently authored authorized differential oracle.

## Tooling and instrumentation recommendations

Use static tools as triage signals, not as the differential oracle. CodeQL has Java/Kotlin default queries and a `security-extended` suite. [10] Semgrep’s Java support includes interfile/interprocedural analysis in its full offering and Maven/Gradle supply-chain analysis; Community Edition has narrower taint/dataflow scope. [11] SpotBugs with Find Security Bugs is a compatible supplemental check for SQL/HQL, command, and XPath injection plus cryptographic weaknesses. [12]

For authorized runtime observation, use JUnit as the repeatable test boundary: the JUnit Platform provides a launcher and test-engine API and integrates with common build tools. [13] Attach the OpenTelemetry Java agent only to a disposable target where HTTP/database edge telemetry helps compare the authorized test run. [14] If targeted hooks are necessary, Byte Buddy supports runtime class generation and can underpin a narrowly scoped test-only agent; keep hooks disabled outside the harness. [15]

## Exact limitations

`available_cases` is source inventory scope, not a count of entries that build, replay, or run in Corsair today. Licenses describe dataset repositories or selected repositories’ default branches; historical revisions and upstream projects require their own review. Framework labels stay generic where public project identity did not clearly identify a framework. The catalog does not infer CVEs, vulnerability predicates, patches, outcomes, exploitability, or validation from repository membership.

**References**

[1]: https://github.com/iris-sast/cwe-bench-java "CWE-Bench-Java repository documentation"
[2]: https://raw.githubusercontent.com/iris-sast/cwe-bench-java/master/data/project_info.csv "CWE-Bench-Java project inventory"
[3]: https://github.com/lin-tan/llm-vul "VJBench replication artifact documentation"
[4]: https://github.com/tuhh-softsec/vul4j "Vul4J dataset documentation"
[5]: https://github.com/tuhh-softsec/VCC-Eval-A-Manually-Curated-Dataset-of-Vulnerability-Introducing-Commits-in-Java "VCC-Eval dataset documentation"
[6]: https://owasp.org/projects/benchmark "OWASP Benchmark project page"
[7]: https://raw.githubusercontent.com/OWASP-Benchmark/BenchmarkJava/master/expectedresults-1.2.csv "OWASP Benchmark Java expected results manifest"
[8]: https://samate.nist.gov/SARD/test-suites/24 "NIST SARD Juliet Java test suite"
[9]: https://github.com/WebGoat/WebGoat "OWASP WebGoat repository documentation"
[10]: https://docs.github.com/en/code-security/reference/code-scanning/codeql/codeql-queries/java-kotlin-built-in-queries "GitHub CodeQL Java and Kotlin queries"
[11]: https://docs.semgrep.dev/languages/java "Semgrep Java support"
[12]: https://spotbugs.readthedocs.io/en/latest/maven.html "SpotBugs Maven and Find Security Bugs integration"
[13]: https://docs.junit.org/current/user-guide/ "JUnit user guide"
[14]: https://opentelemetry.io/docs/zero-code/java/agent/ "OpenTelemetry Java agent"
[15]: https://bytebuddy.net/ "Byte Buddy runtime code generation"
