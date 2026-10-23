**Ruby external-realism backlog for Corsair.** The catalog records **220 advisory-backed vulnerability candidates** from exact public Ruby Advisory Database YAML paths plus **15 project-corpus candidates**. It is a research intake, not a benchmark result: every JSON candidate is marked `validation_status: "candidate"`; nothing here was cloned, installed, reproduced, patched, or tested.

**Author:** Manus AI

## Sources and case intake

The strongest Ruby-specific seed is the [Ruby Advisory Database][1]. It stores advisories as YAML files below gem and Ruby-engine directories, with CVE or GHSA identifiers, version ranges, descriptions, and upstream URLs. The catalog links **220** exact filenames spread across Rails components, Rack, parser/sanitizer, authentication/OAuth, servers, job queues, uploads/archives, standard-library components, and CRuby/JRuby/mruby. This selected-target inventory contained 500 advisory paths; that observation is not a source-wide count and, importantly, is not a runnable-example count. Its contribution terms place contributor-owned submissions in the public domain but expressly warn that some OSVDB-derived material has separate terms. [1] [17]

Use the [GitHub Advisory Database][2] and its official global-advisory API to refresh candidates. The API can filter reviewed advisories by `ecosystem=rubygems` and exposes affected version ranges, first patched version when known, CVEs/GHSAs, CWEs, severity, and references. GitHub’s database is CC BY 4.0 and imports, among other sources, Ruby Advisory Database records. [2] [3]

[OSV.dev][4] is the complementary live resolver: it aggregates OSV-format databases and supports package-version and commit-hash queries. It helps check a locked dependency graph against a specific version or commit, but its aggregation does not establish that a test is reproducible. The [CVEfixes v1.0.8 dataset][5] is a patch-oriented expansion source: it covers 12,107 fixing commits across 11,873 CVEs and 4,249 projects overall through 23 July 2024 under CC BY 4.0. The 12.7 GB release does **not** publish a Ruby subset count on its landing page, so the catalog does not claim one. Filter its relational data and independently inspect each upstream revision before treating any row as a Ruby lead. [4] [5]

The project-only entries deliberately broaden coverage beyond Rails: Rails, Sinatra, Hanami, Grape, Roda, Padrino, Rack, Puma, Sidekiq, and application-scale projects such as Discourse, Spree, Decidim, Forem, Redmine, and Chatwoot. Rails is a modular MVC framework; its components can also be used separately. [6] Sinatra’s routing and middleware run over Rack. [7] Hanami is full-stack but made from smaller components and documents separate unit and integration suites. [8] Grape, Roda, and Padrino provide API, routing-tree, and Sinatra-derived alternatives. [9] [10] [11] These project entries are **not vulnerability claims**.

## Triage and safe differential verification

1. For each advisory candidate, preserve the advisory URL and fetch the upstream source at a tagged affected release. Confirm that the gem/engine version is within an advisory’s affected range and that the lockfile, Ruby engine/version, operating system, database/service version, and test fixture are pinned.
2. Prefer a minimal authorization-safe fixture over an exploit. Define an observable oracle appropriate to the case, such as status/body/headers, authorization result, redirected destination, parsed object, escaped output, exception class, process exit/signal, resource ceiling, or a deterministic filesystem/database state. Run that fixture on an affected and a patched version under matching inputs and normalize time, randomness, ports, and network access.
3. For dependency coverage, run `bundler-audit` against `Gemfile.lock`; RubyGems documents that it checks the lockfile against ruby-advisory-db and recommends CI use. Add OSV-Scanner as an independent lockfile/dependency view rather than treating either scanner alert as proof of exploitability. [12] [13]
4. For Rails sources, record Brakeman JSON/SARIF output as a secondary signal, not an oracle. Brakeman is a Rails security scanner and supports Rails 2.3.x through 8.x, but its own confidence levels are not proof that a candidate is exploitable. [14]
5. Instrument behavior during the controlled test. Ruby’s `TracePoint` can target call, return, raise, rescue, C-call, thread, fiber, and script-compilation events; select only required events and note that tracing is per Ractor. Pair it with explicit response/side-effect capture. [15] Start SimpleCov before application code to report line/branch execution and use its test tracking only as coverage evidence, never vulnerability validation. [16]

## Exact limitations

- The candidate IDs identify **public advisory records**, not confirmed Corsair cases. An advisory may lack a public fix commit, require a complex service/dependency setup, have an unavailable historical release, describe a native-engine issue, or be unfit for a safe deterministic oracle.
- No candidate has an asserted CVE patch, PoC, trigger, expected result, or vulnerable/fixed test outcome in this work. The JSON does not invent those details.
- A shared CVE can appear under more than one Ruby Advisory Database package path. The catalog preserves paths as `rubysec:<directory>/<project>/<CVE>` rather than silently deduplicating cross-component advisory records. Downstream selection should de-duplicate by underlying vulnerability where appropriate.
- The project-corpus entries are explicitly named `project:*` and are not vulnerability cases. Repository availability and license status must be rechecked at use time.
- Advisory data and package metadata change. Re-read the linked record, upstream release notes, repository license, and current security policy immediately before downloading, building, or executing an authorized fixture.

**References**

[1]: https://github.com/rubysec/ruby-advisory-db "Ruby Advisory Database repository"
[2]: https://docs.github.com/en/rest/security-advisories/global-advisories "GitHub global security advisories REST API"
[3]: https://github.com/github/advisory-database "GitHub Advisory Database repository"
[4]: https://google.github.io/osv.dev/ "OSV introduction"
[5]: https://zenodo.org/records/4476563 "CVEfixes Dataset version 1.0.8"
[6]: https://github.com/rails/rails "Ruby on Rails repository"
[7]: https://github.com/sinatra/sinatra "Sinatra repository"
[8]: https://github.com/hanami/hanami "Hanami repository"
[9]: https://github.com/ruby-grape/grape "Grape repository"
[10]: https://github.com/jeremyevans/roda "Roda repository"
[11]: https://github.com/padrino/padrino-framework "Padrino repository"
[12]: https://guides.rubygems.org/security/ "RubyGems security guidance"
[13]: https://google.github.io/osv-scanner/ "OSV-Scanner documentation"
[14]: https://github.com/presidentbeef/brakeman "Brakeman repository"
[15]: https://docs.ruby-lang.org/en/master/TracePoint.html "Ruby TracePoint documentation"
[16]: https://github.com/simplecov-ruby/simplecov "SimpleCov repository"
[17]: https://raw.githubusercontent.com/rubysec/ruby-advisory-db/master/LICENSE.txt "Ruby Advisory Database license terms"
