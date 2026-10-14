# permissive-reduced corpus

Permissive-licensed (MIT / BSD / Apache / ISC) vulnerability/fix pairs, each reduced from an upstream
open-source project to a small offline-runnable module in the same shape as `benchmarks/corpus/infosec-harness/`.
Imported under the corpus-import thread (branch `claude/project-thread-a7mob0`), 2026-10-14.

## What is imported

- Only the application code is reduced, and it is derived verbatim from the upstream project at its pinned
  pre-fix (vulnerable) and fix (fixed) commits. Packaging, docs, upstream tests and dependencies are removed so
  each tree builds and runs offline in its runtime-matrix image; any removed dependency is noted per family.
- No exploit or proof-of-vulnerability code is authored here. The benign control and proof-of-vulnerability
  probes are authored by the Corsair chain at run time.
- Each upstream project keeps its own licence. Every family is SPDX-checked individually at its pinned fix
  commit and only permissive upstreams are included; the licence is recorded in the family's `provenance.json`.

## Layout

`<language>/<family>/{a,b}/` — variant dirs `a` and `b`; the letter does not reveal which variant is vulnerable
(recorded only in `manifest.json`). `manifest.json` is the evaluator-only answer key (each entry's `finding.repo_url` uses the `eval-corpus/` prefix, the sentinel intake resolves against this manifest's own directory) (one entry per variant) and
never enters an agent input. Each family has a `provenance.json` with its upstream repo, parent + fix commits,
SPDX licence, NVD CWE, pointer source and what the reduction removed.

## Families

| Family | Language | CWE | Upstream | Record | Licence |
| --- | --- | --- | --- | --- | --- |
| dot-prop | javascript | CWE-1321 | sindresorhus/dot-prop | CVE-2020-8116 | MIT |
| angular-http-server | javascript | CWE-22 | simonh1000/angular-http-server | GHSA-4rvg-955w-h68q | Apache-2.0 |
| codecov-node | javascript | CWE-78 | codecov/codecov-node | CVE-2020-15123 | MIT |
| rubyzip | ruby | CWE-22 | rubyzip/rubyzip | CVE-2018-1000544 | BSD-2-Clause |
| rack-static | ruby | CWE-22 | rack/rack | CVE-2025-27610 | MIT |

## Pointer sources

The CVE-to-commit pointers come from public vulnerability datasets used as metadata only (SecBench.js for
JavaScript); none of those datasets' code is included. See each family's `provenance.json`.
