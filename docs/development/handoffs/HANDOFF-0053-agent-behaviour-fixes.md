---
id: HANDOFF-0053
kind: handoff
title: Agent behaviour fixes
status: recorded
updated: 2026-10-13
related: [PLAN-0035, PLAN-0031, PLAN-0034, PLAN-0025, PLAN-0029, PLAN-0030]
---

# Agent behaviour fixes

## Verified state

Branch `claude/agent-behaviour-fixes-f1h06f` from main `0d9bb5a`, PR #34. Delivered (details in PLAN-0035): planner skill read-once budget guidance (`test-planning-v3`); `--stage-profiles` for the fixture E2E CLI with `evals/fixture_e2e/stage-profiles.json` (identification 8192; planning and authoring 8192 with a 2048 thinking budget; assessment 16384 with a 2048 thinking budget); authoring hides `write_test_file`/`run_tests` via native tool `prepare` after a `workspace_failure` or a spent run budget, and its skill keeps the security test's planned direction (`test-authoring-v3`, `test-authoring-config-v2`); assessment refuses `reproduced`/`not_reproduced`/`verified` without a cited witness item of the right revision (`evidence-assessment-v4`). Gates and contract shapes are unchanged. Nothing is qualified.

## Validation and blockers

- `make test-config`: 788 passed (one existing deprecation warning). New checks were confirmed to fail on the old agent code. Scripted authoring evals 12/12. CI green on each pushed head.
- Live before/after on RIG0 (PLAN-0035 tables): planning 0/4 to 4/4 plans with no cap hit; planner evals 6/12 to 12/12 completed (10/12 pass every assertion; `unsupported_observation` returns ready); authoring 2/3 return blocked after one refused run (1/3 invented an output tool); assessment v4 1/3 admitted equal to the gate, 2/3 hit the cap while drafting the right answer. The assessment thinking budget (`31f503f`) was added after that and its live rerun was still running at this handoff.
- Fully live chains on the reviewed workspace did not reach assessment (0/2); the inverted-polarity guard is unmeasured until the sandbox runner (PR #33) is on main.
- Private evidence: `.runs/behaviour-20261013/` in `/home/al/git/corsair-behaviour` (before) and `/home/al/git/corsair-pr34` (after) on RIG0; both worktrees left in place.

## Decisions and next steps

Reasoning budgets are operator stage profiles, not agent code. Only `workspace_failure` hides authoring tools deterministically. Read tools keep zero retries. In composition, a live assessor that over-claims twice without a witness now fails its stage; its proposals stay in the receipt. Next:

1. Three live assessment repeats with the thinking budget.
2. Once PR #33 and this PR are on main, rerun the fully live sandbox chain with `--stage-profiles` and check security test polarity.
3. Decide whether the planner should refuse a test id whose file differs from its test path, and whether an invented output-tool name gets one retry.
4. Freeze held-out planner cases before more prompt tuning (`unsupported_observation`).

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then PLAN-0035 and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. On RIG0 against llm.almckay.io, run three live assessment repeats with evals/fixture_e2e/stage-profiles.json, then (with the sandbox runner from PLAN-0034 on main) the fully live chain with the same profiles, checking security-test polarity. Do not change the gates or feed the gate ruling back to agents. Run make test-config, keep evidence under .runs/, update PLAN-0035/CURRENT.md and write a new handoff.
```
