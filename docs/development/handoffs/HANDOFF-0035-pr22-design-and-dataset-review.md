---
id: HANDOFF-0035
kind: handoff
title: PR22 design and dataset review
status: recorded
updated: 2026-10-12
related: [PLAN-0018, ISSUE-0007]
---

# PR22 design and dataset review

## Verified state

Reviewed [PR22](https://github.com/X-McKay/corsair/pull/22) at exact head `28feef4c29b3683bad5656bb52357213ce3031ad`, with clean main starting at `fce6e1be3ba351aa681562e0acb58085355f5a10`. The PR proposes agent/evaluation specs and adds a rubric-coded dataset; it changes no agent/runtime implementation. Main was not switched or merged. Its native canary, immutable JSPWiki source capture and unexecuted test draft remain as recorded in HANDOFF-0034. Resolve the commit containing this review checkpoint from Git rather than assuming its future SHA.

The user explicitly requested review comments. The [posted review](https://github.com/X-McKay/corsair/pull/22#pullrequestreview-5494630076) is COMMENTED, bound to the exact head; no merge or approval was submitted. It adds two inline design findings and endorses the existing per-attempt calibration-label finding without duplicating it. The missing-handoff requirement remains applicable to the PR author despite no runtime work; a future PR handoff must use the next unused ID on then-current main.

## Validation and blockers

An isolated exact-head source archive under `.runs/pr22-review-20261012/checkout` preserved main. Its pyproject/lock bytes match the installed pinned environment. The four new rubric checks passed/0.36s; the complete offline suite passed367/6.44s with one existing event-loop warning. No live provider, Temporal, sandbox or downloaded project execution occurred. GitHub reported zero check runs on this PR head at review time; local success is not CI evidence. Installed Pydantic Evals2.55.0 dataset/judge/report evaluator source and relevant published ISSUE-0007 findings were inspected.

Findings: case-level historical failure unions cannot be ground truth for individual retained outputs; unsupported planner output currently requires a complete executable test pair, conflicting with honest abstention; selecting and assessing a judge threshold on the same calibration sample is not pre-registered validation. The inline comments propose status-specific Pydantic contracts and a separate frozen confirmation set after any exploratory calibration. The PR remains open and its specs remain drafts. No semantic calibration, baseline or skill promotion was run or admitted.

Private review payload, posted review response, checkout and test log are retained under `.runs/pr22-review-20261012/`; none belongs in Git. Final record/link checks passed4/0.04s and diff whitespace checks passed on the documentation checkpoint, separately from the367 exact-PR-head checks.

## Decisions and next steps

When updates arrive, fetch the new immutable head, inspect the exact diff and verify that calibration labels identify individual outputs and preserve provider failures separately. Check the unsupported branch and calibration ordering, handoff numbering, current-main integration and actual CI. Repeat affected offline checks before commenting further. Current user scope authorizes comments, not merging PR22. Existing broader development authorization and the one-owner runtime rule remain unchanged.

PLAN-0021's next implementation gate remains the concrete confined dependency/source/test/report recipe from HANDOFF-0034. ISSUE-0007 stays blocked; this review does not reopen live inference or alter any policy, pins or budgets.

## Continuation prompt

```text
Read AGENTS.md, README.md, docs/development/CURRENT.md, Corsair review/development/handoff skills and HANDOFF-0035 (plus HANDOFF-0034 for runtime/corpus state). Verify local/remote state and PR22's current head/comments. Review updates against the posted exact-head findings without assuming they are fixed or that local tests establish semantic qualification. Run proportionate offline checks and post only new actionable feedback within the requested review scope; do not merge without authorization. Preserve unrelated work and private evidence, update records/CURRENT and append a new handoff for substantial follow-up work.
```
