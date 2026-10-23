# Python benchmark sources for Corsair

**The catalog records 122 candidates: 100 concrete vulnerability IDs from the public Vul4Py inventory and 22 deliberately marked project-only candidates.** Every item remains a `candidate` for Corsair. This research did not clone a revision, install dependencies, run an exploit, run tests, or confirm a patch outcome.

## Highest-value source-backed backlog

**Vul4Py is the immediately usable external-realism source.** Its repository publishes a 100-row `vuln_id, repo_url, fix_commit` inventory, and the project describes 100 Python vulnerabilities: 92 CVEs and 8 GHSAs. It also describes vulnerable/fixed checkouts, a baseline test set, and an exploit test set for every entry. The catalog carries all 100 exact inventory identifiers and the linked upstream commit as *unexecuted Corsair candidates*, not as Corsair-valid cases. The benchmark project's own claim of paired oracles must be rerun in an authorized, isolated environment before adopting an instance. [1] [2]

**CVEfixes is the scalable historical source.** Version 1.0.8 reports 11,873 CVEs, 12,107 fixing commits, 4,249 projects, and 272 CWEs through 23 July 2024; its release includes an SQL database and before/after file and function information. Those counts are across languages, so they must not be reported as Python cases. Filter its relational data to Python changed files/methods and public repositories, then prove each selected parent/fix pair locally. Dataset data are CC BY 4.0 and its collection code is MIT; each mined project retains its own license. [3]

**MoreFixes is a larger mining backlog.** Its published v1 snapshot reports 26,617 CVEs, 31,883 fix commits, and 6,945 GitHub projects through 24 January 2024, with a PostgreSQL dump and patch archive. The reported count is language-independent. Treat it as discovery material only until Python scope, repository licensing, parent revision, and a local differential oracle are established. [4]

**PyPA, GitHub, and OSV provide current selection and cross-reference feeds.** PyPA's advisory database is a CC-BY-4.0 public inventory for PyPI packages. GitHub's global-advisory endpoint supports `ecosystem=pip` and returns GHSA/CVE identifiers, package data, affected ranges, patched-version information, references, and CWEs. OSV aggregates databases that use the OpenSSF Vulnerability format and supports version/commit queries. These sources supply provenance and affected-version metadata, not executable proof. [5] [6] [7]

**OWASP Benchmark for Python is complementary, not a real-vulnerability source.** It is a GPL-3.0 preliminary v0.1 runnable Python web app intended to score SAST, DAST, and IAST tools. Use it for harness/instrumentation calibration and score parsing, but do not label its intentional flaws as historical CVE/GHSA examples. [8]

## Framework breadth

The JSON adds 22 **project candidates only** spanning WSGI/ASGI web applications (Django, Flask, FastAPI, Starlette, Sanic, aiohttp, Pyramid, Tornado, Falcon, Bottle, CherryPy, web.py), evented networking (Twisted), distributed work (Celery), APIs/templates (Django REST Framework and Jinja), data/database and validation libraries (SQLAlchemy, Pydantic, pandas, Dask), crawling (Scrapy), and an HTTP client (Requests). They are public upstream repositories, not asserted vulnerabilities. Their licenses must be checked per selected revision; metadata for a few repositories does not expose a current SPDX ID.

## Recommended authorized differential-verification stack

Use an isolated local clone and pinned interpreter/dependencies. For each selected candidate, record the upstream source URL, parent/fixed commit, lockfile or resolved dependency set, platform, command, and timeout. Run a **functional oracle** against parent and fixed revisions, then a minimal **security oracle** expected to distinguish them. Do not scan third-party infrastructure or send unapproved traffic; dynamic tests should target only the local authorized service/container.

Use `pytest` for reproducible test selection and separate baseline/exploit suites; it can target an individual node ID and returns a result code when invoked from Python. [9] Run it under `coverage.py` with branch coverage and per-test contexts where practical, preserving JSON or LCOV evidence that the intended vulnerable and patched paths actually execute. [10]

Run **Bandit** as a lightweight AST-based Python security signal and keep the report beside the differential verdict; it is not an execution oracle. [11] Add **Semgrep** for pattern and taint-oriented comparison, being explicit that its deeper Python framework analysis is a product-tier capability and that rule licenses matter. [12] Use **pip-audit** in JSON mode for dependency exposure; it supports PyPI and OSV services and should be saved as supply-chain context, not confused with first-party code verification. [13] For locally runnable web fixtures only, OWASP ZAP's documented automation options can provide a DAST signal after explicit authorization. [14]

## Exact limitations

The 100 Vul4Py CVE/GHSA strings and commit links are source-backed by that benchmark's canonical CSV, but **none was executed or validated by Corsair in this task**. CVEfixes and MoreFixes counts are their publishers' multi-language totals, not Python-only totals. Advisory feeds may contain incomplete, revised, withdrawn, or non-reproducible records and often lack a runnable test. A fixing commit may not be the sole semantic repair. Framework project entries are diversity seeds only and must never be counted as vulnerability cases. Dataset licenses do not override upstream repository or dependency licenses.

The machine-readable backlog is at `benchmarks/catalog/python.json`; its `kind` field distinguishes `real_vulnerability_dataset_candidate` from `project_candidate_not_vulnerability_case`.

## References

[1]: https://github.com/tabudz/vul4py "Vul4Py repository and canonical case inventory"
[2]: https://arxiv.org/html/2608.00692v1 "Vul4Py benchmark description"
[3]: https://zenodo.org/records/4476563 "CVEfixes Dataset record"
[4]: https://zenodo.org/records/11199120 "MoreFixes Dataset record"
[5]: https://github.com/pypa/advisory-database "Python Packaging Advisory Database"
[6]: https://docs.github.com/en/rest/security-advisories/global-advisories "GitHub global security advisories REST API"
[7]: https://google.github.io/osv.dev/ "OSV introduction and API infrastructure"
[8]: https://github.com/OWASP-Benchmark/BenchmarkPython "OWASP Benchmark for Python"
[9]: https://docs.pytest.org/en/stable/how-to/usage.html "pytest invocation and test selection"
[10]: https://coverage.readthedocs.io/ "Coverage.py documentation"
[11]: https://bandit.readthedocs.io/en/latest/ "Bandit documentation"
[12]: https://semgrep.dev/docs/languages/python "Semgrep Python support"
[13]: https://github.com/pypa/pip-audit "pip-audit project documentation"
[14]: https://www.zaproxy.org/docs/ "OWASP ZAP documentation"
