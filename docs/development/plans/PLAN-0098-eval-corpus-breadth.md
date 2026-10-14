---
id: PLAN-0098
kind: plan
title: Ten eval cases per agent per language, one directory per case
status: in_progress
updated: 2026-10-14
related: [SPEC-0023, SPEC-0035, SPEC-0067, SPEC-0078, ISSUE-0010]
---

# Ten eval cases per agent per language, one directory per case

## Objective and dependencies

The owner asked for at least ten isolated eval cases for every agent in every supported language (Python, Java, JavaScript, Ruby, Perl), from open-source examples where usable and targeted synthetic cases otherwise, and then for a simpler, scalable eval layout: `evals/<agent>/<language>/<set>/<case>/` plus `evals/e2e/<language>/<set>/<case>/`. Base: main `df5c661` (PR #130 merged), so new planning, authoring and assessment cases use the SPEC-0078 unit-test contract (typed observations, no witness, outcome-blind validity review). Production code is unchanged; every gap a case exposes is recorded in [ISSUE-0010](../issues/ISSUE-0010-eval-breadth-production-gaps.md) instead of being worked around in eval code.

One case is one frozen directory with its own agent input and evaluator-only oracle that `make eval AGENT=<agent> SET=<set>` scores. Repeats are not cases. Retired sets (the suite refuses them), pending sets (fail today for a recorded production gap) and issue requests run with `corsair run` are listed apart and not counted.

## Steps

- [x] Inventory cases per agent and language on `df5c661` (table below).
- [x] Search for usable open-source material with independent agents; record provenance and licence for every imported example and skip unclear or incompatible licences.
- [x] Add a `breadth` set per agent with distinct behaviours per language (positives, negatives, injection, refusals, transfer shapes); no padding.
- [x] Move every agent eval set, unchanged, to `evals/<suite>/<language>/<set>/<case>/{input,oracle,case}.json` with a frozen manifest per set (`evals/cases.py`); add `EVAL_LANGUAGE=` to `make eval`.
- [x] Move end-to-end data (fixture chain cases, Jest cohort, the corpus issue requests and the two negative requests) to `evals/e2e/<language>/<set>/`.
- [x] Guards: every set loads and matches its manifest, no unlisted case directory, held-out case ids never cited under `docs/development/` (`tests/configuration/test_evaluation_layout.py`).
- [x] Run every scripted set and the offline suite; record results.
- [ ] Owner review of the draft PR; live runs of the new sets on RIG0 when the owner chooses.

## Inventory

Before (main `df5c661`; one language-free identification case counted under Python then):

| Agent | Python | Java | JavaScript | Ruby | Perl |
| --- | --- | --- | --- | --- | --- |
| environment | 7 | 1 | 0 | 0 | 0 |
| identification | 7 | 0 | 0 | 1 | 0 |
| planning | 14 (incl. 12 in retired held-out sets, not run) | 0 | 0 | 0 | 0 |
| authoring | 12 | 0 | 0 | 0 | 0 |
| assessment | 32 | 0 | 0 | 0 | 0 |

After (`python -m evals.inventory`):

| Agent | Python | Java | JavaScript | Ruby | Perl | common |
| --- | --- | --- | --- | --- | --- | --- |
| environment | 11 | 13 | 12 | 11 | 11 | 0 |
| identification | 10 | 10 | 10 | 11 | 10 | 1 |
| planning | 14 | 10 | 10 | 10 | 10 | 0 |
| authoring | 12 | **0** (10 pending) | **0** (10 pending) | 10 | **0** (10 pending) | 0 |
| assessment | 32 | 11 | 11 | 11 | 11 | 0 |
| e2e (chain) | 5 | 0 | 2 | 0 | 0 | 0 |

Python planning's 14 are development 6, the held-out set still in use 6, unit 2; the two retired held-out sets (6 each) are not counted.

Shortfalls:

- Authoring Java, JavaScript and Perl: the ten behaviours per language are written (`breadth_pending`) but `TestAuthoringInput` admits pytest and Minitest test ids only, and Java/Perl also lack an assertion reader (PR #128 carries the Perl one; the per-framework reader registry is a lane 4 follow-up). They count once those land and the set is re-frozen as `breadth`.
- Assessment Java, JavaScript, Ruby and Perl cover the pre-execution validity review only. Post-execution gate-evidence cases need real base runs from each language's runner, as the Python cases have; none were captured.
- End-to-end cases are not part of the per-agent target; they are listed for the inventory.

## Provenance

Every case's `case.json` records source, commit, path and licence.

| Source | Licence | Used for |
| --- | --- | --- |
| [X-McKay/infosec-harness](https://github.com/X-McKay/infosec-harness) `52aa2ac`, 14 non-held-out Java, JavaScript and Perl families (checked by script against `evals/corpus/held_out.json` without printing names) | same owner; in-repo copy under SPEC-0067 (`benchmarks/corpus/infosec-harness/SOURCE.md`) | identification 15, planning 13 |
| [github/codeql](https://github.com/github/codeql) `b6a9c9a` (`tainted_path.py`, `TaintedPath.java`, `SqlTainted.java`, `ZipSlipBad.java` shape) | MIT | identification 3, planning 1 |
| [vercel/ms](https://github.com/vercel/ms) 0.7.0 `dc61e2f` (ReDoS) | MIT | identification 1, planning 1 |
| [sinatra/sinatra](https://github.com/sinatra/sinatra) v2.0.0 `5de6498` and rack-protection v2.0.1 `4831ab6` | MIT | identification 1, planning 1 |
| Corsair-authored synthetic cases | n/a | environment 50, identification 24, planning 24, authoring 40, assessment 44 |

Evaluated and not used: OWASP Benchmark and WebGoat (GPL), SecBench.js (no licence), Juliet Java, CWE-Bench-Java, vulpy and the Ruby gems surveyed (usable licences, not imported in this pass), Perl modules under Artistic-1.0/GPL dual licence (owner decision pending). Downloads were kept in their own directories and read with `python3 -I` scripts outside them; nothing downloaded was run or imported. No held-out corpus family was opened.

## Validation and progress

See [HANDOFF-0133](../handoffs/HANDOFF-0133-eval-corpus-breadth.md) for the commands and actual results of every scripted set and the offline suite. Scripted mode replays each oracle through a `FunctionModel`: it proves plumbing, oracle consistency and evaluator sensitivity, not agent quality. No live model run was made.

## Decisions and next action

- Layout decided with the owner 2026-10-14: agent/language/set, `common` for language-free cases, one manifest per set, set identity = SHA-256 of the manifest, held-out = a manifest flag guarded by one shared test, baselines kept per set and language (`<set>.<language>` labels). Existing cases moved byte-for-byte in content; their `dataset_sha256` values change once because identity is now the manifest digest, so promoted baselines compare as a new identity until re-promoted.
- `EVAL_LANGUAGE` instead of `LANG` (the locale variable).
- Legacy non-agent suites (`repository_identification`, `issue_analysis`) keep their YAML; the imported corpus stays verbatim under `benchmarks/corpus/`.
- Next: owner review; then live `make eval` of the breadth sets per agent on RIG0 to set first baselines; then convert `authoring/breadth_pending` once ISSUE-0010's authoring items land.
