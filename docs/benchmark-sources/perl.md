**CPANSA is the strongest public seed for Perl realism:** its current export contains **1,060 distinct advisory IDs** over **440 distributions**. It stores affected/fixed version expressions, optional CVE aliases, and source references in distribution YAML, which is enough to identify concrete cases without asserting that any has been reproduced. The companion `cpan-audit` tool consumes this database and can inspect a distribution, installed tree, `cpanfile`, or Carton snapshot. [1] [2]

**Author:** Manus AI

## Catalog outcome

`benchmarks/catalog/perl.json` contains **84 candidate entries**: **66 exact CPANSA advisory IDs** and **18 explicitly non-vulnerability project candidates**. The advisory slice spans 21 Mojolicious, 4 Plack, 3 Dancer, 6 Dancer2, 6 CGI, 14 Catalyst-family, 1 Template Toolkit, and 11 Mojolicious-extension records. Every advisory row retains an authoritative CPANSA source URL, stated ranges, aliases, report date, and listed-reference count. Project rows deliberately say `project_candidate`; they make no claim that a project has a vulnerability.

The broader CPANSA export is the expansion queue. It has **2,052 distribution-level records**, which reduce to **1,060 unique IDs** because an advisory can appear in more than one distribution context. Prioritize rows with an upstream fix reference, a release tarball or reachable historical revision, a version range, and an input path that can be tested locally. The CPAN Security Group is the CNA for Perl and CPAN, while the Perl security policy describes the core interpreter and modules maintained in the core repository as its scope. [3] [4]

## Source use

Use CPANSA as the primary inventory and its dedicated YAML record where retained, otherwise the authoritative JSON export, as the first citation for each candidate. Reconcile assigned CVE aliases and later references against the official CVE List V5, then use NVD’s CVE/change-history APIs only as corroboration. CVE List V5 is the official CVE archive; it requires processing both CNA and, where present, CVE Program containers. NVD cautions that older records may be less detailed. [5] [6]

GitHub Advisory Database and OSV are useful supplementary indexes, but neither is a complete CPAN benchmark source. GitHub documents no CPAN package ecosystem in its supported list, and OSV says it is an aggregator whose corrections belong upstream. Treat a matching GHSA or OSV record as a link to inspect, not proof that a Perl package, revision, or test condition is in scope. [7] [8]

The selected repository pool broadens the backlog beyond web microframeworks: Perl core, PSGI servers/middleware, identity and access management, ticketing, publishing, integrated library systems, wiki and mailing-list software, HTTP/LDAP clients, and tooling. It is intentionally useful for independently generated synthetic examples as well as later source-history reconstruction, but remains separate from the CPANSA case count.

## Differential-verification setup

Pin each experiment to a release tarball or immutable commit together with the Perl version, OS image, and dependency lock. Carton stores dependency versions in `cpanfile.snapshot`; `carton install --deployment` uses that snapshot rather than falling back to changing dependency resolution. Run `cpan-audit deps` as a dependency-context check, not as a behavioral oracle. [2] [9]

Use TAP as the primary behavioral artifact: preserve the test command, exit status, TAP, stderr, request/response fixture, and a normalized observable output from vulnerable and fixed revisions. `Test::Harness` exposes a programmable test summary, supports `prove --timer`, parallel harness options, and `HARNESS_PERL_SWITCHES=-T` for taint mode. Run dangerous handling paths only against non-secret fixtures and loopback services in an isolated, unprivileged workspace. [10]

For execution reachability, use `Devel::Cover` with a narrow project-path selection and archive its coverage database alongside the TAP result. It reports statement, branch, condition, subroutine, and pod coverage; coverage is evidence that the chosen path ran, not evidence of exploitation or remediation. Add `Devel::NYTProf` only when a timing or algorithmic-complexity differential matters; it supports per-line and per-subroutine profiling and process-specific output. [11] [12]

## Exact limitations

- **No candidate was cloned, built, patched, executed, or validated in this research.** `validation_status` is uniformly `candidate`.
- An advisory inventory record is **not** a runnable benchmark. Some records lack a CVE, fixed version, upstream commit, or a still-buildable historical dependency graph. Some CPANSA rows also describe bundled or external-component exposure rather than a flaw in Perl source.
- The `1,060` and `2,052` counts are a retrieval-time snapshot of the CPANSA export, not a promise that every record is public, safe to reconstruct, applicable to a particular operating system, or suitable for a differential oracle.
- This report does not infer CVEs, commits, patches, test outcomes, or exploitability beyond the source inventory. Admit a case only after an authorized, non-destructive local reproduction distinguishes pinned vulnerable and fixed baselines.

## References

[1]: https://github.com/briandfoy/cpan-security-advisory "CPAN Security Advisory Database"
[2]: https://metacpan.org/dist/CPAN-Audit/view/script/cpan-audit "cpan-audit command documentation"
[3]: https://security.metacpan.org/ "CPAN Security Group"
[4]: https://perldoc.perl.org/perlsecpolicy "Perl security report handling policy"
[5]: https://github.com/CVEProject/cvelistV5 "Official CVE List V5"
[6]: https://nvd.nist.gov/developers/vulnerabilities "NVD Vulnerability APIs"
[7]: https://github.com/github/advisory-database "GitHub Advisory Database"
[8]: https://google.github.io/osv.dev/faq/ "OSV frequently asked questions"
[9]: https://github.com/perl-carton/carton "Carton dependency manager"
[10]: https://perldoc.perl.org/Test::Harness "Test Harness documentation"
[11]: https://metacpan.org/pod/Devel::Cover "Devel Cover documentation"
[12]: https://metacpan.org/pod/Devel::NYTProf "Devel NYTProf documentation"
