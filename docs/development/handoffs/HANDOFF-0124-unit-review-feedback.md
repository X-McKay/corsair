---
id: HANDOFF-0124
kind: handoff
title: Outcome-blind unit-test review
status: recorded
updated: 2026-10-13
related: [SPEC-0078, PLAN-0093]
---

# Outcome-blind unit-test review

## Verified state

Work begins at PR #130 head fa4726f3549da91f64f1aa2e4e8d4f1745af16f2 on codex/unit-test-first-validation. Resolve the commit containing this handoff with Git. User authorized addressing review feedback and updating the existing PR, without merging. Unrelated HANDOFF-0118/0119 files and their CURRENT paragraph remain outside this change.

The existing assessment agent now has a separate outcome-blind validity invocation after tests freeze and before investigation execution. Its typed input admits source, patch, plan and issue artifacts only. Trusted finalization binds that review to source/plan/patch identity; disposition assessment cannot create or change it. Both native probes still execute on each investigated revision. Semantic review remains model judgment; this is not independent runtime attestation.

Optional evidence explicitly showing the target was not reached invalidates the claim regardless of effect status. Matching observation kinds and revision differentials alone do not establish calibration or source linkage. Generic skills/contracts retain dependency doubles and real application seams without mandatory recorders.

Fixture cases capture candidate source, and measured framework assertion facts reach planning/authoring as harness data. Pre-execution evidence avoids execution inventory overhead and path-header truncation; source reads can focus on relevant calls and helpers, while complete test/plan/condition reads remain required. Source acquisition still has a 16,384-character per-file envelope, and evidence has finite item/total/tool budgets. Missing necessary source remains unsupported; these changes do not qualify arbitrary-size repositories.

SPEC-0075/PLAN-0090 were renumbered SPEC-0078/PLAN-0093, and the historical HANDOFF-0120 became HANDOFF-0123, following review-reported reservations. Historical uncommitted-state text is explicitly a snapshot, not current state.

## Validation and blockers

Final full offline command: `PYTHONPATH=src:. env -u NO_COLOR TERM=xterm /tmp/corsair-pr-review/venv/bin/python -m pytest -n 4 tests/configuration tests/unit tests/agents tests/temporal/test_fixture_contracts.py tests/temporal/test_issue_analysis_composition.py tests/temporal/test_chain_composition.py`: **2108 passed, 6 skipped, 12 inherited warnings in 60.26 seconds**. Log `.runs/pr130-review-feedback/full-offline-final.log`. A subsequently added native durable-converter test for the review/input union passed separately (1 passed, 8 deselected; `durable-review-payload.log`). No implementation changed after the full pass. Development record checks and shared/assessment skill metadata validation passed; `git diff --check` is clean.

Frozen legacy scripted sets remain planning12/12, authoring20/20, assessment54/54. Official `python -m evals.run <agent> --set unit` runs: planning2 cases/4 successful attempts, authoring2 cases/4 successful attempts (default repeat2), assessment7 cases/7 successful attempts (repeat1). No task or evaluator failures. Reports live under ignored `.runs/evals/<agent>/20261013T*-{development,unit}-scripted/`; this worktree has no promoted baseline for the new unit sets. Legacy counts match prior retained reports. Changed-boundary subagent tests251passed, final dataset/mock regression7passed, split-focused59passed. Scripted results establish plumbing/evaluator sensitivity only.

Retained failed attempts: initial full run4failed/2102passed/6skipped because the new ordering test incorrectly included authoring development execution; corrected to check frozen baseline/candidate execution. Initial restricted-sandbox async runs stalled and were interrupted; host retries passed. An initial workflow test command used the wrong directory (exit4); then a plan status `active` failed the record guard and was corrected to `in_progress`. Subagent fixture tests initially had an async marker issue and a held-out assertion accidentally applied to the new unit set; both corrected before the reported pass. Prior test logs and scripted reports were copied to ignored `.runs/pr130-review-feedback/prior-evidence/` with a SHA-256 manifest. Raw evidence remains local and is not committed.

The attempted live planner evaluation was rejected by automatic approval review because the external endpoint https://llm.almckay.io/v1 was not explicitly authorized to receive prompts. No bypass or retry was attempted; live authoring/assessment evaluation was not attempted after that rejection. Live semantic quality and promoted live-baseline comparisons remain unqualified. Docker/OpenShell and historical Temporal replay are not claimed by offline checks.

## Decisions and next steps

Use frozen unit-mode agent sets alongside unchanged legacy baselines. Scripted results validate contract/evaluator behavior, not model judgment. Run live unit-mode comparisons only after the user explicitly approves the destination, using existing operator configuration and budgets; retain failures without promoting a baseline automatically. Keep publication limited to the authorized PR; no merge or deployment.

## Continuation prompt

```text
Read AGENTS.md, CURRENT.md, SPEC-0078, PLAN-0093 and HANDOFF-0124. Inspect PR #130, git/source state and the retained evidence. Preserve exactly two executed probes, outcome-blind pre-execution validity review, immutable source/plan/patch binding and generic dependency boundaries. Continue bounded qualification using existing agent eval sets. Live calls to the configured endpoint need explicit user approval following the automatic-review rejection. Do not reintroduce required low-level recorders or equate scripted success with semantic quality. Preserve unrelated review records, run proportionate checks, and update records with actual results.
```
