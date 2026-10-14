---
id: HANDOFF-0133
kind: handoff
title: Eval breadth sets and the agent/language/set layout
status: recorded
updated: 2026-10-14
related: [PLAN-0098, ISSUE-0010, SPEC-0023, SPEC-0078]
---

# Eval breadth sets and the agent/language/set layout

## Verified state

Branch `claude/eval-corpus-breadth-88ptmq` from main `df5c661` (PR #130 merged), with develop `58c2d9b` merged in; PR #131, retargeted to `develop`. Delivered:

- A `breadth` set per agent: environment 50, identification 44, planning 40, authoring 10 (Ruby), assessment 44 validity-review cases for four non-Python languages (now `assessment/breadth_pending`, ISSUE-0010 item 7), plus `authoring/breadth_pending` (30 cases for JavaScript, Java and Perl that fail today for ISSUE-0010 items 1 and 2). Inventory before and after, shortfalls and provenance are in [PLAN-0098](../plans/PLAN-0098-eval-corpus-breadth.md).
- Every agent set moved to `evals/<suite>/<language>/<set>/<case>/{input,oracle,case}.json` with `evals/<suite>/sets/<set>.json` manifests ([evals/README.md](../../../evals/README.md)); `evals/cases.py` loads and freezes sets, `evals/inventory.py` prints the agent x language table, `make eval ... EVAL_LANGUAGE=<language>` narrows a run.
- End-to-end data moved to `evals/e2e/` ([README](../../../evals/e2e/README.md)): `python/fixture` (5 chain cases), `javascript/jest` (2 benchmark ids), `python/corpus` (the 17 corpus issue requests with their `repository.git`; `issue.json` is now `input.json`, `expected.json` is `oracle.json`), `python/corpus_negative` (2 requests; their answer keys moved from a README table into `oracle.json`).
- Develop's new single-file sets moved into the same layout during the merge: environment `development-v2`, planning `unit-v2` and `unit-first`, assessment `unit` (structured validity v2; the original seven frozen as `unit-v1`, refused by the suite) and `unit-transfer`. Their evaluators keep develop's evaluator versions; only `dataset_sha256` changes to the set digest.
- Production source under `src/` is unchanged.

Path changes others will notice: `corsair run --issue-json evals/corpus/issues/<case>/issue.json` is now `--issue-json evals/e2e/python/corpus/<case>/input.json`; `python -m evals.corpus.issues --set corpus-python` is now `--set corpus`. `capture()` still writes `issue.json`/`expected.json` under any `--root`, so the paused campaign entry (which imports only `capture`) is unaffected. Every moved set's `dataset_sha256` changes once (identity is now the manifest digest), so a promoted baseline under `.runs/evals/` compares as a different identity until a new run is promoted.

## Validation and blockers

Scripted `make eval` on this branch (oracle replay through `FunctionModel`, real requests blocked; plumbing and oracle consistency, not agent quality):

| Agent | Set | Clean attempts |
| --- | --- | --- |
| environment | development / breadth | 16/16 / 100/100 |
| identification | development / breadth | 16/16 / 88/88 |
| planning | development / heldout3 / unit / breadth | 12/12 / 12/12 / 4/4 / 80/80 |
| authoring | development / unit / breadth | 20/20 / 4/4 / 20/20 |
| authoring | breadth_pending | 0/30 passed, exit 2 (expected; every case refused as input, ISSUE-0010) |
| assessment | development / held_out / unit / breadth (before the merge) | 54/54 / 21/21 / 7/7 / 44/44 |
| after merging develop `58c2d9b` | assessment unit / unit-transfer / development; planning unit-v2 / unit-first / breadth; environment development-v2 / breadth; identification breadth; authoring breadth; chain fixture | 7/7 / 3/3 / 54/54; 4/4 / 12/12 / 80/80; 16/16 / 100/100; 88/88; 20/20; 5/5 |
| chain | fixture | 5/5 |

Development, held-out and unit counts equal the runs of the same sets before the move. `make eval AGENT=planning SET=breadth EVAL_LANGUAGE=ruby` gave 20/20. Offline suite (`make test-config`) after merging develop `58c2d9b`: 2576 passed; `make test-v2`: 3 passed. Unrun: every live (`PROVIDER_CONFIG`) eval, the `jest` cohort (live Docker only), any `corsair run` of the moved corpus requests (validated offline only: each input parses as an `IssueRequest` and its revisions exist in its `repository.git`).

## Decisions and next steps

- Layout as agreed with the owner on 2026-10-14; held-out is a manifest flag guarded by `tests/configuration/test_evaluation_layout.py`, which also refuses unlisted case directories.
- Authoring Java, JavaScript and Perl stay short of ten until `TestAuthoringInput` accepts every admitted runner's id grammar and the per-framework assertion reader registry lands (ISSUE-0010). Then rename the pending cases into `breadth`, re-freeze, and run.
- Assessment non-Python post-execution cases need captured base runs from each runner first; the pending validity cases need reviewed structured reviews (ISSUE-0010 item 7).
- D11 (v1 code leaves develop): the per-case data stays; the next PR from this thread converts it into the v2 agent sets per `/mnt/project-files/notes/v2-eval-layout-and-baselines.md`.
- Live runs on RIG0 per agent and set give the first real numbers for the breadth sets; several identification and planning oracles are judgement calls to review against that first run.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then PLAN-0098, ISSUE-0010 and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. If the owner asks for live numbers, run `make eval AGENT=<agent> SET=breadth PROVIDER_CONFIG=<config>` per agent on RIG0 (host-only), review any failing oracle before changing it, and record the results. When ISSUE-0010 items 1 and 2 land on main, move evals/test_authoring/*/breadth_pending cases into breadth, re-freeze with `python -m evals.cases test_authoring breadth --freeze`, and run the set. Run make test-config, update PLAN-0098/CURRENT.md, and write a new handoff.
```
