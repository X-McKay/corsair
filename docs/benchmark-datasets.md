# Benchmark datasets and qualification plan

Research date: 2026-10-10. This document adds candidate coverage, not supported runtime claims, to the design baseline.

## Recommendation

Use existing executable vulnerability benchmarks where available, and curate a small set of upstream advisory/fix pairs for the remaining ecosystems. Keep this as a versioned collection of data consumed by Pydantic Evals and the normal investigation graph. Do not introduce another agent framework, orchestration service, or benchmark platform.

The [JSON inventory](../benchmarks/candidate-cases.json) contains **50 distinct issue candidates**: 10 Java/Maven, 10 Python, 10 JavaScript, 10 Perl, and 10 Ruby. The [CSV](../benchmarks/candidate-cases.csv) is a compact review view. Every case is marked `candidate` and `runtime_qualified=false`. Source records were inspected; none of these repositories or exploits was executed during this research.

Maven is a Java build-system requirement. The ten Maven cases also count as ten Java cases, not twenty independent examples. A vulnerable revision and its fixed counterpart are one issue pair. These 50 candidates could eventually supply 100 revision-level investigations, once both sides are qualified. They do not constitute ten cases for every individual framework within each language.

## Sources and verified coverage

| Source | Coverage inspected | Evidence supplied | Recommended role |
| --- | --- | --- | --- |
| [Vul4J](https://github.com/tuhh-softsec/vul4j) | Current CSV: 129 entries; **79 PoV entries, including 70 Maven and 9 Gradle** | Fix links, PoV tests, build/test commands, required Java compliance level; current harness offers cached OCI setup | Primary Java/Maven source. Use PoV entries; exclude the 50 SpotBugs-only entries from exploit-validation scoring |
| [Vul4Py](https://github.com/tabudz/vul4py) | CSV: **100 Python issues**; README identifies 92 CVEs and 8 GHSAs | Repository and fix revision; preparation scripts and paired functional/exploit oracles | Strong Python candidate source, conditional on license and oracle qualification |
| [SecBench.js](https://github.com/cristianstaicu/SecBench.js) | **600 package records** in inspected tree | Vulnerable npm package, advisory links, Jest exploit test, fixed-version/fix links where available; some Dockerfiles | Strong JavaScript candidate source, conditional on license and package-to-repository mapping |
| [CPANSA](https://github.com/briandfoy/cpan-security-advisory) | **403 distribution YAML files**; selected ten distinct issue records | Descriptions, affected/fixed requirements, references, sometimes exact fix commits and repository URLs | Primary Perl candidate pool; recover upstream tests and qualify each pair |
| [Ruby Advisory Database](https://github.com/rubysec/ruby-advisory-db) | **1,263 gem advisory YAML files**; selected ten distinct CVEs | Preconditions, patched requirements, advisories, sometimes fix commits | Primary Ruby candidate pool; recover upstream tests and qualify each pair |
| [CVEfixes](https://github.com/secureIT-project/CVEfixes) | v1.0.8 reports **11,873 CVEs, 12,107 fix commits, 4,249 projects, 272 CWEs** | Before/after code and relational links at CVE, repository, commit, file, and method levels | Licensed cross-language discovery and metadata fallback; no general executable-oracle guarantee |
| [MoreFixes](https://github.com/JafarAkhondali/Morefixes) | Current README points to [2026 v4 release](https://zenodo.org/records/20776007) | Mined fix candidates, confidence scores, patches, PostgreSQL dump | Expansion source after initial suite. Respect fix-link confidence and inspect changes rather than treating a score as ground truth |

Counts of advisory files are **not** counts of runnable tests, unique repositories, or independently validated vulnerabilities. Perl files can contain several advisories; Ruby CVE/GHSA records may be aliases. The CVEfixes aggregate counts do not establish ten executable cases in a particular language.

Vul4J's current README reports successful reproduction of its 79 PoV entries in a May 2026 image build. That is upstream evidence, not proof that those entries work under our kind/OpenShell policy. Its historical JDK 7/8/11/16 and build overlays exceed our initial Java 17/JUnit 5 support envelope. Admit runtime profiles individually; do not rewrite historical cases to claim Java 17 support.

SecBench.js README describes five categories: prototype pollution, ReDoS, command injection, path traversal, and code injection. The inspected tree has 192, 97, 101, 170, and 40 package records respectively, totaling 600; README gives 98 ReDoS and 169 traversal. Pin the inspected source revision and record this discrepancy.

## Additional datasets for specific components

- [OWASP BenchmarkJava](https://github.com/OWASP-Benchmark/BenchmarkJava): version 1.2 has [2,740 synthetic cases across 11 categories](https://owasp.org/www-project-benchmark/), with expected true/false findings and Maven execution. Useful for deliberate false-positive calibration and test-oracle checks. It is a runnable servlet application, not an issue-to-repository benchmark; its labels alone do not qualify our two unit tests or establish deployment exploitability.
- [OpenSSF CVE Benchmark](https://github.com/ossf-cve-benchmark/ossf-cve-benchmark): over 200 real JavaScript/TypeScript CVEs with vulnerable/patched source metadata and an MIT-licensed benchmark harness. A useful alternative metadata source if SecBench.js licensing remains unresolved. Its built-in objective is SAST comparison, so recover or write runtime oracles before using it for exploit confirmation.
- [SWE-rebench V2](https://huggingface.co/datasets/nebius/SWE-rebench-V2): current card reports 32,079 general software-engineering tasks, including Java, Python, and JavaScript, with execution-environment material in its [builder](https://github.com/SWE-rebench/SWE-rebench-V2). Useful for environment discovery and ordinary bug reproduction. The current card's language list does not include Ruby or Perl; do not infer those from older mirrors. General bug outcomes are not security ground truth.
- [NIST SARD / Juliet](https://samate.nist.gov/SARD/test-suites/): synthetic good/bad examples can exercise deterministic oracle and report logic. They supplement real repositories and do not close the Perl/Ruby reproducibility gap.

## Licensing and provenance

Public accessibility is not an open-source license grant. Separate licenses for metadata, benchmark tooling, upstream source, tests, and redistributed images.

| Source | Inspected license/provenance | Admission consequence |
| --- | --- | --- |
| Vul4J | Dataset CC-BY-4.0; harness GPL-3.0 | Preserve attribution and qualify target-repository licenses; using dataset metadata does not require adopting the entire harness |
| CVEfixes | Data CC-BY-4.0; collection code MIT | Prefer published data over rerunning a large mining pipeline; retain source attribution |
| CPANSA | Repository Artistic-2.0 | Retain notices; upstream CPAN distribution/source licenses remain separate |
| Ruby Advisory Database | Contributions public-domain dedication; database warns of legacy OSVDB copyrighted material | Selected inventory uses CVE records, not OSVDB-named records; still inspect per-record provenance. [GitHub Advisory Database](https://github.com/github/advisory-database) metadata is an alternative with CC-BY-4.0 terms |
| Vul4Py and SecBench.js | No explicit license file found in inspected repository trees | Keep as research candidates. Resolve terms before copying tests/tooling or distributing derived benchmark artifacts; use licensed upstream/advisory alternatives when necessary |
| OpenSSF CVE Benchmark | MIT harness license | Check source repository and embedded-data provenance individually |
| OWASP BenchmarkJava | GPL-2.0 repository license | Preserve applicable notices/terms when incorporating or redistributing it |
| SWE-rebench V2 | Dataset card CC-BY-4.0 | Retain attribution and verify underlying repository/image terms |

Inventory source links pin the inspected repository tree revisions. An upstream fix URL is a claim requiring review; `vulnerable_reference` intentionally remains unset until the actual baseline is selected and reproduced. Never infer that every fix's first parent is a complete vulnerable benchmark checkout.

## Candidate variety and limitations

The inventory covers Java XXE, resource exhaustion, traversal, access control, command injection, CSRF, unsafe deserialization, SSRF, and sensitive logging. Python candidates include HTML sanitization, XML parsing, ReDoS, command injection, JWT key confusion, cookie-prefix handling, multipart limits, proxy credential leakage, and client file disclosure. JavaScript selects two cases from each of the five SecBench.js categories. Ruby candidates cover Rack file inclusion, Rails XSS/CSP/SQL issues, Sinatra redirect decisions, archive resource limits, sanitization, Paperclip SSRF, OAuth secret disclosure, and Sprockets traversal. Perl candidates cover tar extraction, YAML deserialization, cookie isolation, session validation, command injection, headers, static-file access, ReDoS, TLS defaults, and SQL comparison logic.

Not all are unit-level or initially supported. TLS, SSRF, database behavior, OAuth controllers, CSRF, and rendering can require application-path fixtures or local services. Test planning must emit `unsupported` or request an explicitly supported application-path recipe when a faithful two-unit-test oracle cannot establish the requested scope. Do not replace the vulnerable implementation with a mock to fit the test format.

Specific source-quality observations:

- CPANSA repeats `CPANSA-Email-Address-2014-01` for different CVEs. The selected record is identified by **CVE-2014-0477**, source revision, and file, not CPANSA ID alone.
- Some inspected CPANSA records have inconsistent fixed-version claims, unrelated references, or missing fixed versions. Those problematic examples were not selected merely to fill the quota. All selected requirements still need upstream confirmation.
- SecBench.js includes missing fixes and ambiguous version strings. The selected ten avoid the inspected unfixed `node-serialize` record and the ambiguous `ansi-regex` fixed-version string. Some selected cases still lack exact fix commits; package versions must be resolved to immutable artifacts and source.
- Vul4Py README's plausible-patch rule allows `functional_rc` equal to **999**. Our qualification requires actual functional/control execution and must never inherit acceptance of absent functional evidence.
- A sanitized string or generated query is a component observation. Browser execution, database semantics, or network reachability require additional evidence before claiming application exploitability.

## Qualification gate

For each issue pair, independently review the advisory, actual source guard/sink, fix, and test oracle. Then:

1. Check provenance and reuse terms. Pin source revisions or package digests, runtime image, dependencies, test framework, architecture, and any compatibility overlay.
2. Establish an evaluator-only reference environment. Discover/install/build from a fresh workspace; record dependency, policy, TLS, and compiler failures separately. Warm-cache success and cold environment-discovery performance are distinct evaluations.
3. Recover the upstream regression test or create a reviewed equivalent using the real implementation. Create one benign control. Record preconditions and allowed observation scope.
4. Freeze the same two-test artifact. The control passes on both revisions; the security safety assertion fails specifically on the vulnerable revision and passes on the fixed one. Upstream exploit-success assertions may have the opposite polarity and must be adapted explicitly. A crash, timeout, skip, missing test, or build failure is not automatically the required security failure.
5. Replay in fresh sandboxes. Require stable assertion results over at least three runs; independently assess timing/resource-based cases under bounded budgets. Preserve all failures. Upstream publication does not substitute for this gate.
6. Repeat under the intended OpenShell policy. Demonstrate that the security effect is observable with a scratch marker or local fixture. Policy denial must not masquerade as a fix. Mark cases requiring unsupported OS behavior, services, or runtimes accordingly.
7. Record immutable receipts and reviewer rationale. Promote to `qualified` only when both revisions and both assertions meet the contract. Keep agent-visible inputs separate from gold revisions, upstream PoVs, and answer keys.

This is benchmark preparation, not a new runtime agent. Use normal source, sandbox, artifact, and execution adapters. A small data-normalization step is sufficient; do not import upstream benchmark orchestration wholesale or run bulk exploit scripts directly on the host.

## Using the cases to evaluate agents

Use each qualified case at several granularities through the existing evaluation contracts:

| Component | Agent-visible input | Evaluator-only reference |
| --- | --- | --- |
| Issue analysis | Advisory converted to a neutral issue plus source revision | Reviewed hypothesis, preconditions, sink/path citations |
| Environment | Source checkout and ordinary manifests/docs/CI | Successful setup recipe and dependency/test-discovery receipts |
| Test planning/authoring | Issue hypothesis and prepared environment | Hidden upstream/reference oracle and vulnerable/fixed comparison |
| Evidence assessment | Frozen receipts and explicitly stated scope | Reviewed disposition, required limitations, contradictory-evidence variants |
| Whole graph | Neutral issue and exact repository | Independently adjudicated result, operational status, traces, resource usage |

Expose recipe data only when evaluating a later agent in isolation; environment discovery gets no evaluator-generated setup hints. Restrict Git history/fix fetches and omit benchmark names, CVE answer keys, and supplied PoVs from blind test-generation runs. Preserve native discovery conventions rather than applying a global rule that strips legitimate project tests. Document residual public-data memorization risk.

Repeat each live-agent case at least three times with fresh workspaces. Score trajectory, contract adherence, correctness, consistency, efficiency, and actual execution separately. Add paraphrased issues, irrelevant dependency alerts, contradictory reports, repository instruction injection, build failures, missing registries, and policy denials as controlled variants with their own labels.

Fixed counterparts measure recognition of a resolved issue. They do not alone measure false-positive rejection for an unrelated or unreachable finding. Add independently reviewed safe/unreachable and disabled-feature cases with stated preconditions; absence of reproduction cannot label a case safe. OWASP labeled negatives can help bootstrap this calibration.

Report per-language, build-system, project, CWE/class, scope, runtime, provider, and execution mode. Keep attempted/completed/blocked/unsupported counts, unsupported conclusive findings, qualified-pair accuracy, tokens, latency, tools, and retry causes. Include qualification coverage so dropping difficult build cases cannot inflate accuracy. Aggregate across projects and show repetitions separately; vulnerable/fixed variants and repeated trials are correlated observations.

## Progressive rollout

1. Start with one supported Java/Maven pair and one Python pair, selected after checking runtime compatibility, alongside existing deterministic failure fixtures. Qualify OpenShell before executing vulnerability workloads there.
2. Qualify two cases per language as ecosystem smoke coverage. JavaScript, Perl, and Ruby extend the initial runtime envelope only when their build/test adapters pass the same gates.
3. Reach **ten qualified distinct issue pairs per ecosystem**, drawing extra candidates if licensing, source quality, unit-test scope, or obsolete dependencies eliminate seeds. Ten is a minimum regression suite, not a statistically strong production benchmark.
4. Freeze a development/held-out split by repository before prompt tuning. If ten pairs cannot support a useful repository-separated holdout, expand the pool rather than presenting a development score as independent evidence. Add reviewed false positives and boundary-failure variants.
5. Run the same qualified cases directly, durably with Temporal, and with OpenShell as those modes are admitted. Compare evidence and failure attribution, not exact command trajectories. Exercise inexpensive direct fixtures frequently and live sandbox suites at component milestones.

This document does not enlarge the current production support envelope. It supplies a concrete route to broader qualification while retaining one graph, one execution contract, and native SDK evaluations.

## Inventory audit and first executable fixture (2026-10-12)

Root/Sol rechecked both inventories:50 distinct candidates, ten per ecosystem; all candidate/runtime-unqualified and all vulnerable references unset. Ten lack exact fixed references;30 have supplied-oracle metadata claims. CSV and JSON shared values/order agree. Java and Python each span nine projects, so related cases must remain together in repository-separated splits. The inventory is preparation material, not fifty passing benchmarks.

The first native two-test fixture now supplies drafted code plus actual discovery, target calls, open witnesses and three fresh vulnerable/fixed repetitions. It uses existing synthetic sources and is explicitly additional to the50 real-project candidates. It provides a minimal semantic baseline before drafting real benchmark patches or evaluating model authorship.

Primary-source shortlist review found concrete admission needs: [Cookiecutter's fix](https://github.com/cookiecutter/cookiecutter/commit/fdffddb31fd2b46344dfa317531ff155e7999f77) changes Mercurial checkout argument handling, so a mocked subprocess assertion cannot demonstrate actual command-injection behavior; a real pinned Mercurial runtime and scratch observation are needed. [JSPWiki's fix](https://github.com/apache/jspwiki/commit/88d89d6523802c044cfcb7930cba40d8eeb21da2) changes forward-page selection and includes JUnit Jupiter tests, making it a Java/Maven admission candidate; a return-string observation alone must not be described as deployed file disclosure. Neither pair was executed or promoted. Start read-only source/environment admission with JSPWiki and retain Cookiecutter as the Python candidate pending runtime compatibility; do not infer vulnerable revision merely from a fix parent.
