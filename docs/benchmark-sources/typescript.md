# TypeScript benchmark-source backlog for Corsair

**Author:** Manus AI

The catalog contains **241 unexecuted candidates**: **223** concrete CVE IDs from the current OpenSSF CVE Benchmark inventory and **18** clearly marked project-only seeds. The CVE entries are a real-world JavaScript/TypeScript ecosystem backlog, not a claim that every entry contains TypeScript or that Corsair has reproduced it. The project seeds are not vulnerability cases at all.

## Primary case sources

The strongest immediately actionable source is the **OpenSSF CVE Benchmark**. Its public repository is MIT-licensed, says it covers JavaScript and TypeScript CVEs, and defines paired pre-patch and post-patch revisions for each CVE. The current public `CVEs/` inventory used to generate the catalog contains 223 JSON manifests. Each catalog entry links directly to its manifest and preserves its CVE ID and listed CWEs. Use the manifest’s upstream repository and two revisions as discovery metadata; first confirm TypeScript-relevant source, installability, a bounded trigger, and an observable differential result. [1]

**SecBench.js** is the best execution-oriented complement. Its public repository documents 600 server-side npm vulnerabilities in five classes: prototype pollution, ReDoS, command injection, path traversal, and arbitrary code injection. It provides package metadata and tests/payloads, and describes sink-location instrumentation. This is particularly useful for designing controlled TypeScript wrappers around real ecosystem failure modes. However, the repository page does not declare an SPDX license, so review permission before copying its tests or payloads. Its own paper describes a payload and success oracle per vulnerability, but that is not a Corsair validation result. [2] [3]

The **GitHub Advisory Database** is a live, public npm discovery source. GitHub publishes acknowledged advisories as OSV files under CC-BY-4.0 and documents GHSA IDs, affected ranges, fix versions, CVE aliases, CWEs, and references. Use reviewed npm records with an upstream fix reference to extend the backlog, but resolve exact package tarballs and commits independently: an advisory is a package-version record, not an executable test. OSV’s affected package, range, version, and reference fields make it suitable for structured ingestion. [4] [5] [10]

**CVEfixes** expands historical discovery beyond npm-focused catalogs. Version 1.0.8 reports 12,107 fixing commits for 11,873 CVEs across 4,249 projects, with repository-, commit-, file-, and function-level data. Its source code is MIT and its data CC-BY-4.0. It is multi-language, so do not count its headline total as TypeScript cases; filter for relevant repositories, then verify each provenance chain against upstream. [6]

Two sources need access or construction before they become usable cases. **TS-VulBench** publicly describes 100 intentionally vulnerable TypeScript files, one weakness per file, but the archive is subscription-gated and its public landing page does not state a reusable data license. **SecJS** supplies an Apache-2.0 collection/evaluation framework, but explicitly does not package its constructed ArenaJS dataset or snapshots. Neither was used to create candidate IDs. [7] [8]

The official **CVE List V5** should be used only as a cross-reference or freshness source. It is updated from the CVE Services API and warns consumers to inspect the CNA container and the CVE Program container when present. It does not certify runtime reproducibility, source language, or a usable patch pair. [9]

## Project-only coverage seeds

The catalog’s 18 project candidates deliberately span server frameworks, full-stack/SSR systems, browser apps, data layers, realtime services, desktop apps, and edge/Bun runtimes: Next.js, Nest, Fastify, Hono, Nuxt, Angular, SvelteKit, Remix, tRPC, Prisma, TypeORM, Socket.IO, Playwright, VS Code, Tauri, Elysia, create-t3-app, and Redwood GraphQL. They are marked `kind: project-candidate`; none asserts a vulnerability, patch, or outcome. The source repositories themselves document TypeScript-oriented coverage for examples including Nest, Hono, Angular, TypeORM, Prisma, and Playwright. [16] [17] [18] [19] [20] [15]

For any project seed, obtain a reviewed GHSA/OSV/CVE record, pin the affected release or commit, retain upstream license notices, and create a minimal local-only fixture. A project candidate becomes a vulnerability candidate only after this provenance step; it becomes a runnable Corsair benchmark only after the differential oracle has actually been run.

## Runtime and oracle recommendations

Use **Node’s built-in test runner** for deterministic TypeScript/Node fixtures where possible. It supports mocks and coverage reporting, including an LCOV reporter; context-scoped mocks restore automatically after the test ends. Record both the vulnerable and fixed run’s exit status, explicit assertion/oracle result, stdout/stderr, and a normalized trace—not merely “no exception.” [11]

Collect line, branch, and function reachability with **c8** when source-map remapping is available. It uses native V8 coverage, can remap generated JavaScript to TypeScript/JSX sources, and can report unexecuted files with `--all`; coverage is evidence that the trigger reached the intended path, not evidence that the security property failed. [12]

For server-side request, outbound-call, and database-style cases, preload a **test-only OpenTelemetry Node SDK** before application code. The official guidance places initialization before the app, supports `--import`, and offers Node auto-instrumentations. Export traces locally and redact secrets, request bodies, and credentials before persisting artifacts. [13]

Add lightweight event probes with stable `node:diagnostics_channel` where the Node runtime exposes relevant events. Named channels and `hasSubscribers` support test-only observation with low/no work when no listener is attached; built-in HTTP events can corroborate request/response behavior. Subscriber callbacks are synchronous, so probes must not mutate the tested application or throw. [14]

For browser-facing and SSR cases, use **Playwright** as the outer oracle: each test gets a fresh browser context, and trace artifacts can capture action, DOM, network, and console evidence. Compare an explicit security-relevant assertion across the pinned vulnerable and fixed revisions; screenshots alone are insufficient. [15]

Keep Node, Bun, Deno/edge-worker, browser, and desktop candidates in separate runtime lanes. Node-specific diagnostics and preload mechanics are not portable. Every lane should deny external network by default, use temporary files and ephemeral local services only, apply a timeout/resource ceiling, and dispose all workers/servers after both runs.

## Exact limitations

Every object in `typescript.json` has `validation_status: "candidate"`. No case in this research pass was checked out, installed, executed, exploited, patched, or validated by Corsair. The 223 OpenSSF IDs are concrete inventory identifiers, but their individual language mix, dependency availability, revision buildability, safe trigger, and reliable fixed-versus-vulnerable oracle remain unverified. No CVEs, GHSAs, patches, commits, framework associations, or test outcomes were invented.

The catalog contains only the two requested data/research artifacts. It does not alter Corsair’s implementation, matrix, other documentation, or Git state.

## References

[1]: https://github.com/ossf-cve-benchmark/ossf-cve-benchmark "OpenSSF CVE Benchmark repository"
[2]: https://github.com/cristianstaicu/SecBench.js "SecBench.js repository"
[3]: https://cispa.de/en/research/publications/71721-secbench.js-an-executable-security-benchmark-suite-for-server-side-javascript "CISPA SecBench.js publication"
[4]: https://github.com/github/advisory-database "GitHub Advisory Database repository"
[5]: https://docs.github.com/en/code-security/security-advisories/working-with-global-security-advisories-from-the-github-advisory-database/about-the-github-advisory-database "GitHub Advisory Database documentation"
[6]: https://github.com/secureIT-project/CVEfixes "CVEfixes repository"
[7]: https://ieee-dataport.org/documents/ts-vulbench-typescript-vulnerability-benchmark-dataset-static-application-security "TS-VulBench dataset landing page"
[8]: https://github.com/SecJS-Vuln-Benchmark/SecJS-Benchmark "SecJS benchmark artifact"
[9]: https://github.com/CVEProject/cvelistV5 "Official CVE List V5 repository"
[10]: https://ossf.github.io/osv-schema/ "Open Source Vulnerability format"
[11]: https://nodejs.org/api/test.html "Node.js test runner documentation"
[12]: https://github.com/bcoe/c8 "c8 native V8 code coverage"
[13]: https://opentelemetry.io/docs/languages/js/getting-started/nodejs/ "OpenTelemetry Node.js instrumentation"
[14]: https://nodejs.org/api/diagnostics_channel.html "Node.js Diagnostics Channel"
[15]: https://github.com/microsoft/playwright "Playwright repository"
[16]: https://github.com/nestjs/nest "Nest repository"
[17]: https://github.com/honojs/hono "Hono repository"
[18]: https://github.com/angular/angular "Angular repository"
[19]: https://github.com/typeorm/typeorm "TypeORM repository"
[20]: https://github.com/prisma/orm "Prisma ORM repository"
