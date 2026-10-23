# C++ benchmark sources

**External-realism backlog: 88 candidates.** It contains 50 exact C++ source-file paths from the official Juliet 1.3 archive, nine Magma target backlogs, and 29 FuzzBench project-driver backlogs. Every catalog entry has `validation_status: "candidate"`. None has been extracted, built, executed, reproduced, or differentially verified for Corsair.

## Public vulnerability datasets

**Juliet C/C++ 1.3** is the best high-volume, license-clear source for small, controlled C++ examples. NIST lists **64,099** C/C++ cases covering **118 CWEs**, distributes the suite under public-domain/CC0 terms, and provides the authoritative archive. The catalog records 50 literal `.cpp` archive paths rather than invented test identifiers. Juliet is synthetic; do not describe any entry as a real CVE or a validated failure. [1]

**Big-Vul** is a public C/C++ security-fix dataset with CVE/CWE information, repository commits, changed files, and before/after versions. Its authors report **3,754** vulnerabilities from **348** GitHub projects spanning **91** vulnerability types. It is useful for selecting historically grounded differential pairs after a record’s commit and dependency state are re-resolved. The repository is MIT-licensed. [2] [3]

**CVEfixes** is the broader source of NVD-linked fix records. Version 1.0.8 reports **11,873 CVEs**, **12,107** fixing commits, **4,249** projects, and method/file pre- and post-change source through 23 July 2024. Its code is MIT and its data is CC BY 4.0. Filter to C/C++ and then verify each candidate because the published total is multi-language. [4]

**DiverseVul** supplies a large C/C++ function-level candidate pool: **18,945** vulnerable and **330,492** non-vulnerable functions derived from **7,514** security-fix commits across **150 CWEs**. The maintained repository makes commit/repository metadata available, but says three commit URLs are missing. Its paper also reports label-noise limitations, so labels are candidates rather than conclusive run-time results. The primary repository does not state a dataset license; the preprint’s CC BY 4.0 license must not be assumed to license the downloaded dataset. [5] [6]

## Real-program and framework repositories

**Magma** is the closest direct source for real-program ground-truth fuzzing. It front-ports reported bugs into maintained library versions and instruments the source to record the distinct states **reached** and **triggered**. The published benchmark reports 118 bugs; its current documentation names libpng, libsndfile, libtiff, libxml2, Lua, Poppler, OpenSSL, SQLite, and PHP. The nine catalog entries are deliberately target-level entries, not claims that any individual Magma bug is reproduced. The reviewed v1.2 tree did not expose a top-level license file, so each component’s license needs checking before reuse. [7] [8]

**FuzzBench** provides 29 reviewed real-world project/driver configurations in its `benchmarks/` directory. It is Apache-2.0 and can use OSS-Fuzz projects as benchmarks. These entries add parsers, image/font/media codecs, crypto, network, database, geospatial, and system-service surfaces, but they are not vulnerability labels. [9]

**OSS-Fuzz** is the best source of current build recipes, harness patterns, seed corpora, and public disclosed artifacts. It supports C/C++ and combines fuzzing engines with sanitizers. Google reported over 13,000 vulnerabilities and 50,000 bugs across 1,000 projects as of May 2025, but disclosure, reproducibility, and continued buildability vary per issue. Only public configurations and disclosed artifacts should enter the authorized backlog. [10]

## Recommended C++ execution signals

Build each pinned candidate with Clang and retain symbols: `-O1 -g -fno-omit-frame-pointer`. Start with **AddressSanitizer** (`-fsanitize=address`) for heap/stack/global bounds, use-after-free, double-free, and invalid-free detection. ASan exits on the first detected error and is a testing tool rather than a production runtime, which makes its non-zero diagnostic outcome useful as a single-run differential observation. [11]

Add **UndefinedBehaviorSanitizer** (`-fsanitize=undefined`) for checks such as signed overflow, invalid shifts, null/misaligned dereferences, and bounds where statically determined. Select extra integer-conversion checks deliberately and record any suppression, because they can identify suspicious but non-undefined behavior. [12]

For structured-input targets, use a narrow deterministic `LLVMFuzzerTestOneInput` harness with `-fsanitize=fuzzer,address` or a separate UBSan build. Seed valid and invalid inputs, minimize with `-merge=1`, pin corpus hashes, and compare only independently observed, symbolized results from the authorized old/new revisions. LibFuzzer is in-process and coverage-guided; its documentation recommends fast, deterministic targets that tolerate arbitrary input. [13]

## Exact limitations

The JSON’s 50 Juliet IDs are source paths in a downloadable archive, not NIST SARD numeric test-case IDs. The 38 Magma/FuzzBench entries are project targets, not vulnerability cases. Big-Vul, CVEfixes, and DiverseVul are catalogued as high-volume selection sources rather than expanded into guessed CVE/commit candidates. No CVE, patch, trigger input, build result, sanitizer finding, reachability result, or test outcome is asserted unless the authoritative source itself states the dataset-level fact cited here. The parent’s synthetic runnable examples remain separate from this external-realism backlog.

## References

[1]: https://samate.nist.gov/SARD/test-suites/112 "NIST SARD Juliet C/C++ 1.3 test suite"
[2]: https://dl.acm.org/doi/10.1145/3379597.3387501 "Big-Vul paper record"
[3]: https://github.com/ZeoVan/MSR_20_Code_vulnerability_CSV_Dataset "Big-Vul primary repository"
[4]: https://github.com/secureIT-project/CVEfixes "CVEfixes primary repository"
[5]: https://arxiv.org/html/2304.00409v2 "DiverseVul paper"
[6]: https://github.com/wagner-group/diversevul "DiverseVul primary repository"
[7]: https://hexhive.epfl.ch/magma/ "Magma benchmark overview"
[8]: https://hexhive.epfl.ch/magma/docs/technical.html "Magma technical reference"
[9]: https://github.com/google/fuzzbench "FuzzBench primary repository"
[10]: https://github.com/google/oss-fuzz "OSS-Fuzz primary repository"
[11]: https://clang.llvm.org/docs/AddressSanitizer.html "Clang AddressSanitizer documentation"
[12]: https://clang.llvm.org/docs/UndefinedBehaviorSanitizer.html "Clang UndefinedBehaviorSanitizer documentation"
[13]: https://llvm.org/docs/LibFuzzer.html "LLVM LibFuzzer documentation"
