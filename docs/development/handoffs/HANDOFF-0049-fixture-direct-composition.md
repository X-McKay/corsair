---
id: HANDOFF-0049
kind: handoff
title: Direct-mode fixture composition
status: recorded
updated: 2026-10-12
related: [SPEC-0031, PLAN-0031, IDEA-0004, SPEC-0027, SPEC-0032, ISSUE-0007]
---

# Direct-mode fixture composition

## Verified state

Branch `claude/fixture-e2e-composition-x59wi3` from main `102fbef`, draft PR #32. Delivered: `src/corsair/composition/evidence.py` (plan and patch to `ObservationPlan` with the agreed mapping, `freeze`, native run to `RunEvidence`, frozen evidence items), `src/corsair/composition/direct.py` (`run_direct`: identification, planning, authoring, frozen baseline and candidate execution, assessment, gates; total routing, no stage retries, swappable `Runners`), `evals/fixture_e2e/` (fixture case with hand-supplied environment evidence, scripted stage models, CLI, and the reviewed host workspace moved from the runner tests). No durable stage, no environment agent, no witness capture. The gate verdict on the fixture is `completed`/`inconclusive`/`not_verified` by design.

## Validation and blockers

- `make test-config`: 754 passed. `tests/agents/test_fixture_composition.py`: 7 passed, including the test-only proof that a captured witness is the only missing gate input.
- PR #32 offline-guards CI green on both commits.
- Live smoke on RIG0 (six runs, Qwen3.6-35B-A3B-NVFP4, cap 16384): results and failures are in PLAN-0031. No run with live upstream stages reached the gate: planning hit the cap in 2 of 4 attempts, and live authoring is refused by the reviewed host workspace by design. Live assessment over real executed evidence over-claimed `reproduced`/`verified` twice, and the gate rejected it both times.
- Blocked: executing model-authored tests needs the OpenShell test workspace (PR #31, SPEC-0032). A reproduced finding or verified fix needs witness capture outside the test process (no design yet).
- Evidence lives under `.runs/fixture-e2e-20261012/` on RIG0, which is private and git-ignored. The worktree `.runs/fixture-e2e-20261012/wt` was left in place.

## Decisions and next steps

Witness stays `None` rather than being inferred from the test's own audit print. The composition lives in `composition/`, not `workflows/`. Next bounded actions:

1. Once #31 merges, build the `Runners` factory over the OpenShell workspace and rerun the fully live variant.
2. Design witness capture owned by the execution node.
3. Hand the planning cap runaway and the author's missing `blocked` on refused workspaces to the planning and authoring owners (ISSUE-0007 family).
4. Add durable E2E-1 after these steps.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then SPEC-0031, PLAN-0031 and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. If PR #31 (OpenShell test workspace, SPEC-0032) is merged and qualified, add a Runners factory over it in evals/fixture_e2e and rerun the fully live E2E-0 on RIG0 against llm.almckay.io; otherwise work on the witness capture design. Do not infer a witness from in-process test output. Run make test-config, preserve evidence under .runs/, update PLAN-0031/CURRENT.md and write a new handoff.
```
