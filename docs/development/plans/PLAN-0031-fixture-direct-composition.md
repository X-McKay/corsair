---
id: PLAN-0031
kind: plan
title: Direct-mode fixture composition
status: in_progress
updated: 2026-10-12
related: [SPEC-0031, IDEA-0004, PLAN-0025, PLAN-0026, PLAN-0027, PLAN-0029]
---

# Direct-mode fixture composition

## Objective and dependencies

Implement [SPEC-0031](../specs/SPEC-0031-fixture-direct-composition.md), step 7 of the IDEA-0004 order (E2E-0, direct only). Depends on the merged stages: identification (PLAN-0024), planning (PLAN-0025), gates (PLAN-0026), authoring and the native pytest runner (PLAN-0027), assessment (PLAN-0029). Independent of the OpenShell test workspace (SPEC-0032/PLAN-0032, parallel thread under `adapters/`), which this plan does not touch; that workspace is what lets a live author's tests execute.

## Steps

- [x] Handoff builder: `observation_plan`, `freeze`, `run_evidence`, `evidence_items` in `src/corsair/composition/evidence.py`.
- [x] Direct composition `run_direct` in `src/corsair/composition/direct.py`, with total routing, per-stage budgets and receipts, gate verdict independent of the assessment agent.
- [x] Fixture case, scripted stage models and CLI in `evals/fixture_e2e/`; reviewed host workspace moved there from the runner tests and changed from `assert` to an explicit refusal.
- [x] Deterministic tests `tests/agents/test_fixture_composition.py`.
- [x] Live run on RIG0 against llm.almckay.io (below).
- [x] Review, CURRENT.md, handoff ([HANDOFF-0049](../handoffs/HANDOFF-0049-fixture-direct-composition.md)).
- [ ] Fully live run with the author's own tests executed, once the OpenShell test workspace (PR #31, SPEC-0032) lands and is qualified.

## Validation and progress

2026-10-12, branch `claude/fixture-e2e-composition-x59wi3` from main `102fbef`: `uv run --locked python -m pytest -q tests/agents/test_fixture_composition.py` 7 passed; runner and authoring suites after the move 67 passed. Scripted CLI run (`python -m evals.fixture_e2e.run --evidence <scratch>`): complete, gate `completed`/`inconclusive`/`not_verified`, proposal admitted; requests/tool calls per stage 2/1, 3/2, 5/4, 8/7. `make test-config` 754 passed (755 after the Codex fixes, 757 after the owner review's evidence-retention fix: the CLI now journals every complete native observation to `native-runs.json`); PR #32 CI (offline-guards) green on both pushed commits.

Live smoke at `669a9ef` on RIG0 (detached worktree, `tests/agents/test_fixture_composition.py` 7 passed there), vLLM at llm.almckay.io serving Qwen3.6-35B-A3B-NVFP4 (every response reported that name), `response_token_limit` 16384, client timeout 180 s, `thinking_mode` server default, default `CompositionBudget`, one output retry, no retries of any run. Three variants, two runs each; usage is requests / tool calls / input tokens / output tokens / seconds:

| Run | Live stages | Ended | Identification | Planning | Authoring | Assessment |
| --- | --- | --- | --- | --- | --- | --- |
| all-1 | all four | authoring: `UnexpectedModelBehavior`, response cap 16384 | 2/1/2917/437/4.1 | 3/2/11803/15808/116.3 | 9/8/39282/19081/141.8 | not reached |
| all-2 | all four | planning: response cap 16384 | 2/1/2929/738/6.5 | 3/2/11632/16799/122.7 | not reached | not reached |
| ip-1 | identification, planning | authoring: output retries exceeded | 2/1/2936/739/6.3 | 3/2/11648/4053/33.9 | scripted | not reached |
| ip-2 | identification, planning | planning: response cap 16384 | 2/1/2935/461/4.2 | 3/2/11692/16834/121.8 | not reached | not reached |
| asm-1 | assessment | complete; proposal rejected | scripted | scripted | scripted | 8/7/43118/3208/28.9 |
| asm-2 | assessment | complete; proposal rejected | scripted | scripted | scripted | 8/7/42559/2708/25.9 |

- Identification was identical in all six runs: ready, `read_document` at `documents.py:3-4`.
- Planning hit the response cap on its final turn in 2 of 4 live attempts, all reasoning tokens; the two completed plans used `AssertionError`/`ValueError` expectations with their own test names (`test_read_document_benign`/`test_read_document_path_traversal`, `test_reads_valid_document`/`test_rejects_path_traversal`).
- all-1 authoring: three write/run cycles, each development run `workspace_failure` with the reviewed workspace's refusal before any interpreter ran (by design). The model then simplified its test, dropping the audit hook, and exhausted the cap on its next turn instead of returning `blocked`.
- ip-1: the scripted author's reviewed test names differ from the live plan's, so discovery did not match and the finalizer refused the patch; the scripted author repeated itself past its one output retry. This variant only works when the live plan reuses the reference names, so it is not a useful repeat.
- asm-1/2 executed the reviewed patch for real (baseline control passed and security failed at line 64; candidate both passed; cleanup confirmed). The live assessor proposed `completed`/`reproduced`/`verified` both times with accurate JUnit citations; the gate permitted `completed`/`inconclusive`/`not_verified` and rejected both proposals (`witness_missing` on both revisions). The assessor did not treat the in-process audit print as insufficient.

No live run reached the gate through live upstream stages. Six runs are a smoke, not qualification. Receipts: `.runs/fixture-e2e-20261012/live-{all,ip,asm}-{1,2}/` on RIG0, with the provider configuration copy at `.runs/fixture-e2e-20261012/provider.json` (no credential).

## Decisions and next action

Witness stays `None`: the gate verdict is inconclusive by design until an execution node captures it. Model-authored tests do not run on the host; the reviewed workspace refuses them, so live authoring stops at `workspace_failure` until SPEC-0032 lands. Execution is already swappable: `run_direct` takes a `Runners` factory returning any `TestRunner` per purpose, so the OpenShell test workspace from draft PR #31 (SPEC-0032) plugs in by building `PytestRunner` over that workspace and the OpenShell execution adapter, with no change here. This PR does not depend on #31; the fully live run (live author's tests executed) resumes once #31 lands and is qualified. Findings for other owners: planning reasoning runs away under the 16384 cap (2/4); the author does not return `blocked` when every development run is refused by the workspace; the assessor over-claims when the only witness is the test's own print, and the gate holds. Next: witness capture design, then the fully live run once #31 lands; stop condition for any verified disposition is a witness captured outside the test process.
