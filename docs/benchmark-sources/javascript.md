# JavaScript benchmark sources for Corsair

**Author:** Manus AI

**SecBench.js is the most immediately actionable external realism backlog:** its public inventory states 600 publicly reported server-side JavaScript vulnerabilities with an exploit payload and success oracle, and its repository keeps each case in a package/version folder with a test and metadata. [1] [2] This catalog pins its 75 named package candidates to SecBench.js commit `5d362353550a8baa42bba34edd26e5fb86d41b60`: 15 inventory locators from each of code injection, command injection, path traversal, prototype pollution, and ReDoS. They are direct source-backed package/version folders, not invented CVE labels. Where a folder's metadata contains a CVE, the catalog preserves it in the candidate note; where it does not, it says so.

`benchmarks/catalog/javascript.json` contains **84 candidates**: **75 SecBench.js package-vulnerability candidates** and **9 explicitly labelled project candidates**. Every entry has `validation_status: "candidate"`. This status deliberately means **not executed or validated by Corsair**, even if the upstream benchmark reports its own exploit or patch checks. It does not claim that a downloaded package, payload, fixed version, patch, or expected test outcome currently works.

## Real-vulnerability inventories

The [OpenSSF CVE Benchmark][3] provides another public, MIT-licensed differential source: its project describes more than 200 real JavaScript/TypeScript CVEs, evaluated on vulnerable and patched code, and includes integrations for ESLint, nodejsscan, and CodeQL. Its 2020 announcement gives the then-current figure as 218 historical CVEs. [3] [4] It is a high-value second pass after SecBench.js because it directly models a vulnerable-versus-patched analysis workflow. Individual OpenSSF entries were not copied into this catalog, so the source is a backlog rather than a false impression of harvested case IDs.

The [GitHub Advisory Database][5] is public under CC-BY-4.0. It stores one OSV-format file per accepted advisory and supports the npm ecosystem; OSV records carry unique GHSA IDs, affected ranges, aliases, and references. [5] [6] [OSV.dev][7] aggregates OSV-format sources and can query a package version or commit. Treat both as refreshable selectors: choose npm advisories in a targeted weakness class, pin the advisory record and package release, then independently build a local authorized fixture. A source advisory alone is not runnable-benchmark validation.

The recent *x.js* paper is a strong scale reference: it reports 1,738 Node.js taint-style advisories through mid-2026, with 1,159 validated exploits across 965 packages in code/command injection, prototype pollution, and path traversal. [8] The accessed primary paper did not expose a public case inventory or artifact license, so the catalog retains x.js as a source record only and does **not** manufacture x.js candidate IDs. [8]

[PoCGen][9] is a public MIT research artifact that consumes GHSA/Snyk identifiers and includes SecBench.js and a 2025–2026 GHSA input list. It can inform harness layout, but it is not used as an independent assertion that a case is valid. [9]

## Framework and application coverage

The 9 `project_candidate` entries provide breadth without misrepresenting repositories as vulnerabilities. Three are intentionally insecure training applications: OWASP Juice Shop (Node.js, Express, Angular), OWASP NodeGoat (Node.js), and DVNA (Node.js with Express, Passport and Sequelize). [10] [11] [12] They are useful local-only fixtures after separate authorization and revision pinning, but their challenge labels are not real-world vulnerability identifiers.

The remaining project candidates are maintained framework/application repositories: Express, Fastify, Koa, Nest, Next.js, and Strapi. They cover minimalist and async middleware, schema-oriented servers, dependency injection, server-rendered React routes, and CMS/API/plugin patterns. The repository/API records establish those projects and licensing metadata. [13] [14] [15] [16] [17] [18] None is presented as a defect report or a runnable vulnerability case.

## Recommended coverage and runtime instrumentation

Use the external cases for **authorized, isolated local differential verification only**. Pin Node, npm/yarn/pnpm, the lockfile, package tarball or git commit, and OS image per run. Keep the fixture in a container or disposable VM with no production credentials, an allowlisted network or no network, a read-only baseline, controlled temporary directory, CPU/memory/time limits, and process cleanup. Record the exact runtime and dependency graph alongside both target versions.

Drive the same request/API or library-call harness against the nominated vulnerable package version and the nominated fixed version. Capture exit status, response/return data, filesystem writes, spawned processes, outbound DNS/HTTP connections, and elapsed time. **Do not treat a vendor `fixedVersion` field as proof:** SecBench.js reports it when available, but Corsair must resolve and compare it independently. [1]

For runtime evidence, instrument source-to-sink boundaries rather than only final assertions: `child_process` (`exec`, `execFile`, `spawn`, `fork`), `vm`, `eval`/`Function`, filesystem read/write and path resolution, URL/HTTP client calls, and prototype/object mutation. Tag request or library-call inputs across async work, and log the actual sink arguments, stack, and effect. Add a watchdog/monotonic timer for ReDoS and define a non-destructive timeout outcome. SecBench.js specifically demonstrates extending Jest with custom dynamic analysis and using common-sink observations such as `exec()` for ground-truth locations. [1] [2]

Cover CommonJS and ESM loading, server routes and middleware, JSON/body/query deserialization, template/rendering paths, background jobs, and SSR/API routes where present. Pre-screen candidates with the OpenSSF-supported ESLint, nodejsscan, and CodeQL integrations, but preserve dynamic traces and the differential oracle as separate evidence because tool findings do not establish exploitation. [3]

## Exact limitations

- The catalog does not include downloaded package fixtures, and **no candidate package has been installed, run, patched, or validated by Corsair**. `validation_status` is intentionally `candidate` for all 84 entries.
- The 75 SecBench.js entries are a balanced subset of its 600-case inventory, not a claim that all 600 will reproduce today. The upstream README's per-class labels differ slightly from the pinned folder layout in the path-traversal/ReDoS split, while the pinned layout still totals 600; this report therefore relies on the total and direct folder locators rather than repeating a disputed class breakdown. [1]
- Source licenses do not automatically license every vulnerable package, fixture, advisory text, proof of concept, or associated test. SecBench.js presently declares no repository license in GitHub metadata; inspect each upstream project's terms before redistributing material. [1]
- IEEE DataPort's **JS-VulBench** describes 1,000 independently constructed one-vulnerability JavaScript files, but requires subscriber login and is intentionally introduced rather than a historical real-vulnerability corpus. It was reviewed but excluded from the public-realism candidate backlog. [19]
- Upstream advisories, packages, ranges, and repositories change or disappear. Re-resolve every candidate against its cited advisory and pin a revision before it becomes a runnable Corsair example.

## References

[1]: https://github.com/cristianstaicu/SecBench.js/tree/5d362353550a8baa42bba34edd26e5fb86d41b60 "SecBench.js public benchmark repository"
[2]: https://cispa.de/en/research/publications/71721-secbench.js-an-executable-security-benchmark-suite-for-server-side-javascript "CISPA SecBench.js publication summary"
[3]: https://github.com/ossf-cve-benchmark/ossf-cve-benchmark "OpenSSF CVE Benchmark repository"
[4]: https://openssf.org/blog/2020/12/09/introducing-the-openssf-cve-benchmark/ "OpenSSF CVE Benchmark announcement"
[5]: https://github.com/github/advisory-database "GitHub Advisory Database repository"
[6]: https://docs.github.com/en/code-security/security-advisories/working-with-global-security-advisories-from-the-github-advisory-database/about-the-github-advisory-database "About the GitHub Advisory Database"
[7]: https://osv.dev/ "OSV distributed vulnerability database"
[8]: https://arxiv.org/html/2610.18585 "x.js live Node.js benchmark paper"
[9]: https://github.com/sola-st/PoCGen "PoCGen npm vulnerability research artifact"
[10]: https://owasp.org/projects/juice-shop "OWASP Juice Shop project"
[11]: https://github.com/owasp/nodegoat "OWASP NodeGoat repository"
[12]: https://github.com/appsecco/dvna "Damn Vulnerable NodeJS Application repository"
[13]: https://api.github.com/repos/expressjs/express "Express repository metadata"
[14]: https://api.github.com/repos/fastify/fastify "Fastify repository metadata"
[15]: https://api.github.com/repos/koajs/koa "Koa repository metadata"
[16]: https://api.github.com/repos/nestjs/nest "Nest repository metadata"
[17]: https://api.github.com/repos/vercel/next.js "Next.js repository metadata"
[18]: https://api.github.com/repos/strapi/strapi "Strapi repository metadata"
[19]: https://ieee-dataport.org/documents/js-vulbench-javascript-vulnerability-benchmark-dataset-static-application-security "JS-VulBench IEEE DataPort record"
