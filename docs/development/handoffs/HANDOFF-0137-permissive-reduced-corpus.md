---
id: HANDOFF-0137
kind: handoff
title: Permissive-reduced corpus import (JavaScript done, Ruby in progress)
status: recorded
updated: 2026-10-14
related: [PLAN-0098, PLAN-0099, SPEC-0082]
---

# Permissive-reduced corpus import (JavaScript done, Ruby in progress)

## Purpose

Grow the v2 whole-chain eval set toward 20 cases per language (10 exploitable +
10 fixed) by importing **existing, labelled** upstream vulnerability/fix pairs,
reduced to small offline trees under `benchmarks/corpus/permissive-reduced/`.
Python already meets the target from the breadth pass; C stays unbuildable
(no runtime row). This pass adds JavaScript and Ruby; Perl is parked.

## Hard rules (unchanged, load-bearing)

- Import existing labelled data only; **no proof-of-vulnerability code is
  authored here** — the Corsair chain writes the control and PoV probes at run
  time. A case that would need an authored PoV is parked and reported.
- **Permissive licences only** (MIT / BSD / Apache-2.0 / ISC), SPDX-checked per
  family at the pinned fix commit; recorded in each family's `provenance.json`.
- Each family is reduced from the pinned pre-fix and fix commits. The
  vuln-responsible logic the fix touches stays **upstream-verbatim**;
  collaborators (process spawn, archive read, minifier, file server) become
  minimal stand-ins that perform the real observable action but decide nothing
  about the property.
- Corpus hygiene: variant dirs `a`/`b`, the letter never reveals which is
  vulnerable (answer only in the evaluator-only `manifest.json`); both variants
  of a pair share title+description; the two variants differ **only** by the
  upstream fix diff, with no fix/CVE/CWE/verdict words anywhere in the
  agent-visible tree (those live only in `manifest.json` and the family-root
  `provenance.json`); `finding.repo_url` carries the `eval-corpus/` intake prefix.

## Division of labour

This corpus thread delivers the `a`/`b` trees + `manifest.json` answer key +
per-family `provenance.json` + `SOURCE.md`. The eval-corpus thread writes and
freezes the `evals/e2e/<lang>/v2/<family>-<a|b>/{input,oracle,case}.json` chain
cases from the trees via `evals/e2e/from_manifest.py`.

## Verified state

On `develop`:

- **JavaScript (3 pairs, merged #167):** `dot-prop` (CVE-2020-8116, CWE-1321,
  MIT), `angular-http-server` (GHSA-4rvg-955w-h68q, CWE-22, Apache-2.0),
  `codecov-node` (CVE-2020-15123, CWE-78, MIT).
- **Ruby (2 pairs, merged #177; chain cases + manifest line fix merged #181):**
  `rubyzip` (CVE-2018-1000544, CWE-22, BSD-2-Clause) and `rack-static`
  (CVE-2025-27610, CWE-22, MIT). The v2 chain set is at 110 cases, Ruby 19.

Merged since (#183): Ruby `ruby-git-fetch` (CVE-2022-25648, CWE-88, MIT) and
`secure-headers` (CVE-2020-5216, CWE-113, Apache-2.0). Provenance-key fix merged
(#184): all Ruby families use `fix_commit`/`parent_commit`.

Batch-3 (this PR): Ruby `tzinfo` (CVE-2022-31163, CWE-22, MIT — identifier-check
anchor, loader require), `cocoapods-git` (CVE-2022-24440, CWE-88, MIT — git
ls-remote argument guard), `pdfkit` (CVE-2022-25765, CWE-78, MIT — shell-string
vs argv-array invocation) and `ruby-git-ls-files` (CVE-2022-46648, CWE-94, MIT —
`eval` vs `EscapedPath` unquoting). Also pins `rubyzip` provenance
`fix_commit`/`parent_commit` from the `v1.2.2`/`v1.2.1` tags to the commit SHAs
`d07b13a6…`/`98f4f2ed…`. Each pair verified offline on the container runtime:
`ruby -c` clean, loads with `-Ilib`, the a/b diff is only the upstream fix, no
leak words, and the property is observable in-process (vulnerable demonstrates it,
fixed does not) with no network. Ruby is at 8 families; permissive + pure-Ruby +
in-process-observable distinct-CWE scarcity makes ~8 the realistic count, not a
clean 10 — reported rather than forced.

## Parked / constrained (findings)

- **Perl:** all surveyed candidates are Artistic-2.0 (non-permissive) — parked
  pending an owner exception; stays at its breadth-pass count otherwise.
- **sanitize** (CVE-2023-36823, CWE-79): the bypass only surfaces through
  nokogiri's C-extension foreign-content parsing — parked (C-extension rule).
- **SSRF (CWE-918):** no clean Ruby candidate — carrierwave delegates to the
  `ssrf_filter` gem (DNS/socket, not in-process); paperclip's fix is a
  config/registration change, not a copyable host check. Both parked.
- **Open redirect (CWE-601):** no clean Ruby candidate — the fixes live in
  framework (Rails) internals, too large to reduce.
- **multi_xml** (CVE-2013-0175, CWE-502): on the Ruby 3.1/Psych 4+ runtime,
  `YAML.load` is safe by default, so the yaml object-injection path is not
  observable; only the `type="symbol"` coercion is (vulnerable returns a Symbol,
  fixed raises `DisallowedTypeError`). Held for the eval thread's judgment on
  whether the symbol-coercion difference is an acceptable PoV before carving.

Consequence: under permissive + pure-Ruby + in-process-observable rules, the
distinct new Ruby CWEs available are 88, 502, 22-via-require, 78, 94 and 113
across six gems. Reaching 10 Ruby families means repeating a CWE across
different upstream projects (allowed; only same-project/same-fix duplication is
disallowed); the real count is reported rather than forced.

## Next

- Batch-3 carved the strongest remaining Ruby candidates (`tzinfo`,
  `cocoapods-git`, `pdfkit`, `ruby-git-ls-files`). Remaining distinct permissive
  pure-Ruby in-process candidates are thin; `multi_xml` stays parked (D14/D16),
  and `cocoapods` hg (CVE-2022-21223) is the same fix commit as `cocoapods-git`
  so it is a same-fix duplicate and is not imported. Report the real Ruby count
  (8) at set close rather than forcing 10.
- Java is handled by a dedicated corpus thread, not this one.
- Each batch lands as a PR against `develop`; the eval thread generates and
  validates the chain cases from it.
