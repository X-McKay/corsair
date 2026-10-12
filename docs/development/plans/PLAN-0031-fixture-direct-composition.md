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
- [ ] Live run on RIG0 against llm.almckay.io.
- [ ] Review, CURRENT.md, handoff.

## Validation and progress

2026-10-12, branch `claude/fixture-e2e-composition-x59wi3` from main `102fbef`: `uv run --locked python -m pytest -q tests/agents/test_fixture_composition.py` 7 passed; runner and authoring suites after the move 67 passed. Scripted CLI run (`python -m evals.fixture_e2e.run --evidence <scratch>`): complete, gate `completed`/`inconclusive`/`not_verified`, proposal admitted; requests/tool calls per stage 2/1, 3/2, 5/4, 8/7.

## Decisions and next action

Witness stays `None`: the gate verdict is inconclusive by design until an execution node captures it. Model-authored tests do not run on the host; the reviewed workspace refuses them, so live authoring stops at `workspace_failure` until SPEC-0032 lands. Next: the live run, then witness capture design (IDEA-0004 step 3 of the coordinator's list).
