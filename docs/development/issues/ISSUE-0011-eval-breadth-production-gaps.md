---
id: ISSUE-0011
kind: issue
title: Production gaps exposed by the per-language eval breadth sets
status: open
updated: 2026-10-14
related: [PLAN-0094, SPEC-0078]
---

# Production gaps exposed by the per-language eval breadth sets

## Observed and expected behavior

Writing ten cases per agent per language (PLAN-0094) exposed places where production code accepts one language less well than the contracts say. None was fixed in eval code; the cases either record the gap in `case.json` or sit in a pending set.

1. **Authoring refuses Jest, JUnit and TAP test ids.** `TestAuthoringInput` validates planned test ids against pytest and Minitest grammars only, so a plan whose ids are `path.js::name`, `pkg.Class#method` or `file.t#subtest` is refused as input (`is not a supported native node id`). The thirty cases in `evals/test_authoring/sets/breadth_pending.json` (ten each for JavaScript, Java and Perl) fail on this today. Expected: the id grammars `ports/test_runner.py` already defines for every admitted runner are accepted.
2. **No Java or Perl assertion reader.** Authoring finalizes assertion lines through per-framework readers; Java has none and Perl's is on draft PR #128. The generic per-framework reader registry (a follow-up to the Perl work on #128) would cover both.
3. **TAP failures carry no exception type.** A failing Test::More assertion reaches the runner as a TAP `not ok` with no typed failure, so Perl plans name a placeholder failure type and assertion-line checks cannot bind.
4. **Post-execution assessment has no non-Python material.** Gate-evidence cases are typed transformations of real runner output; only pytest base runs exist (`evals/evidence_assessment/base/`). Java, JavaScript, Ruby and Perl assessment cases therefore cover the pre-execution validity review only.
5. **Self-observation admission reads Python only.** The authoring stage's self-observation check parses Python and admits other files unread, so `stage_admitted` is omitted from non-Python authoring checks.
6. **Environment discovery ids for Maven are unverified.** Java environment oracles assume Surefire reports `pkg.Class#method`; no captured Surefire output confirms the form for both JUnit 4 and 5.

Eval-side limits found at the same time, not production defects: the environment checks raise `KeyError` when a ready output names a field the oracle lacks (the run still fails, but as an evaluator failure); identification has no `unsupported` oracle; Ruby and Perl environment sets have no discovery-failure case; older-runtime ready cases exist for Java and Python only; several identification and planning oracles are judgement calls that need review after the first live run; planning discovery commands in the new cases are illustrative and were never executed.

## Reproduction and evidence

Branch `claude/eval-corpus-breadth-88ptmq` on main `df5c661`:

```sh
make eval AGENT=authoring SET=breadth_pending   # 0/30, every case refused as input; pending.json names the reason
PYTHONPATH=src:. .venv/bin/python -m pytest -q tests/configuration/test_breadth_authoring.py
```

## Attempts and diagnosis

Items 1 and 2 were confirmed by running the pending set; items 3 to 6 by reading the runner, assessment base material and admission code while writing cases. No production change was attempted (out of scope for PLAN-0094; generic fixes belong to the owning lanes).

## Resolution criteria and next action

Resolved per item when the production change lands on main and the matching eval cases pass in scripted mode: for 1 and 2, `breadth_pending` re-frozen as part of `breadth` and passing; for 4, captured base runs from each runner and gate-evidence cases built from them. Next action: lane 4's reader registry after #128, then the authoring id grammar.
