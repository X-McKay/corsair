---
id: PLAN-0024
kind: plan
title: Narrow issue identification baseline
status: complete
updated: 2026-10-12
related: [SPEC-0024, SPEC-0022, PLAN-0018, PLAN-0023, ISSUE-0007]
---

# Narrow issue identification baseline

## Objective and dependencies

Implement SPEC-0024 as a small independently evaluated replacement for the hypothesis analyst. User authorization accepts the narrower objective and prioritizes reliable end-to-end evidence over latency. Existing source/provider/SDK seams suffice. Old analyst/reviewer contracts and histories remain separate.

## Steps

- [x] Add strict draft/final identification contracts, one native factory and mandatory procedural skill.
- [x] Freeze a deterministic selection corpus and dimensioned native Pydantic Evals; verify meaningful negative cases and native skill/tool/output delivery.
- [x] Run smallest offline checks and affected suite, then a bounded provider smoke only after source/input/config freeze.
- [x] Record actual results, qualification limits, downstream contract migration and continuation.

## Validation and progress

Starting clean local and remote main: `0f1abab6379f2a9332d1a476552cf4c1ded3d97b`. The bounded implementation and three frozen provider comparisons are complete; final v3 passed all checks on 16/16 attempts. The analyst's original semantics gate stays blocked; old evidence is not modified.

## Decisions and next action

Use trusted verbatim report preservation plus a read-grounded implementation location. Do not generate an execution explanation. Keep the new factory isolated while measuring it; do not change the existing workflow's return type or connect the unqualified reviewer. Replace the prior judge-calibration dependency for this role with frozen deterministic case expectations. Real-project admission, exactly-two-test validity and final disposition gates remain unchanged.

Candidate v1: offline383/6.77s; 23-input freeze ed891335a46481f1afc884ca0d9a84cd176c80ff2f08f3083c297a4689bbbaf5. Live001 completed16/16, raw all-check7/16. Six exact excerpt-boundary flags were evaluator limitations, one same-name decoy choice was a genuine localization defect, and two MaxModelRequests flags were double-counted evaluation metrics; actual requests were within4. No original result is rewritten. V2 removes report generation entirely, preserves the full issue in trusted output, adds generic body/relevance guidance, and separates observed counters from native metrics. Localization oracles and budgets remain unchanged. Focused v2 checks14/1.14s include a native metric/receipt equality regression.

Candidate v2: offline383/6.84s; 24-input freeze bdc23315e58b926e20d320c135ed3b1eb6533fd12a27ac2730076f6c350897d9. Live002 completed15/16, all15 passing deterministic checks; one request for storage.py lines1–80 exceeded its actual two-line source and was correctly refused with toolretry0. V3 changes only the stage-owned reader interface to a fixed at-most80-line window with a tool-computed EOF endpoint, retaining path/start refusal and unchanged output/corpus/budgets. Initial v3 scripted tests omitted a citation end_line during the tool-signature edit (retained failures); the fixture response was corrected and all21 focused checks pass/1.16s. No live request was made with the faulty scripted fixture.


Candidate v3: final offline preflight (the Makefile `test-config` suite) passed 390 checks in 6.88s. The native provider command `PYTHONPATH=src:. .venv/bin/python -m evals.issue_identification.evaluate --evidence .runs/issue-identification-20261012/live-003 --provider-config .runs/issue-identification-20261012/provider.json` completed 16/16; all outputs passed every deterministic check, with zero native/evaluator failures, unknown tools or output corrections. All 25 frozen source/config/corpus/test inputs and copies match manifest ef7bf4ab4da199038c56e9f24cc9e335a8f59639abcd67a9fd201bfda49141e6 after execution. Native metrics match receipts. See the [qualification report](../../qualification/issue-identification.md) for complete telemetry, retained prior failures and scope limits.

Final review checked the typed boundary, current-run source provenance, oracle isolation, tool authority and failure accounting. No unresolved code blocker was found for this isolated baseline. This completes PLAN-0024's bounded deliverable; independently reviewed fresh cases, native durable admission and the separate planner/test execution composition are not qualified. ISSUE-0007 remains blocked for end-to-end admission. Next: freeze fresh localization cases and implement the read-only planner boundary from SPEC-0022 before connecting admitted stages. The user explicitly authorizes publishing reviewed work to main.
