---
id: PLAN-0038
kind: plan
title: Test planner prompt v4 and read guard
status: in_progress
updated: 2026-10-13
related: [PLAN-0036, PLAN-0035, PLAN-0025, SPEC-0022, SPEC-0023]
---

# Test planner prompt v4 and read guard

## Objective and dependencies

Respond to the PLAN-0036 findings so the SPEC-0022 planner can be qualified: re-reads that exhaust the tool-call budget, reads of the approved (to-be-created) test path, fixtures in `tmp_path.parent`, ready plans for concerns no listed facility observes, `safe_behavior` contradicting `required_behavior`, and witnesses claiming events the facility never records. This is the first step toward running every example and benchmark end to end; the planner stays disconnected from other stages until it is qualified. Inference only (local model at llm.almckay.io from RIG0); no kind cluster.

## Steps

- [x] Prompt `test-planning-v4` (skill and rendered prompt): approved test paths are listed separately as files to create and are not readable; read-once wording with a stop condition; a step deciding whether a listed facility observes the sensitive operation itself (a test outcome, exception or return value never shows that an operation did not happen), with unsupported as a correct result and no substitution of an observable property; a scratch example that keeps the outside file inside the scratch location; `safe_behavior` must identify the behavior `required_behavior` states; witnesses only for events the facility actually records for that call (in-process audit hooks do not see what a launched shell does); no forecast of test outcomes on current source; source references cover the whole implementation. v3's "decide each field instead of weighing alternatives" is removed.
- [x] Structural read guard (`test-planning-config-v2`): native tool preparation (`FunctionToolset.prepared`) withdraws `read_source` once every inventory line has been returned in the current run, so a re-read of a fully read inventory cannot be requested and the output tool is the only call left. Scoped to the planner; the shared window reader and other stages are unchanged.
- [x] Offline tests: the reader is offered until the inventory is covered and withdrawn after; prompt lists approved paths as unreadable.
- [ ] Fresh held-out cases (second held-out set) written and independently reviewed by agents other than the prompt author, then frozen by manifest before any provider sees them.
- [ ] Live on RIG0, sequential, each once, no retries: development × v4 (2 repeats, compare with PLAN-0036's v3 4/12); the exposed first held-out set × v4 (3 repeats, comparison only); the fresh held-out set × v4 (3 repeats, qualification decision).
- [ ] Review of every actual plan and error; records, `CURRENT.md`, handoff.

## Pre-registered criteria

Provider profile as PLAN-0036: saved RIG0 provider configuration, `response_token_limit` 8192, `thinking_token_budget` 2048, timeout 180 s. Budgets unchanged (5 requests, 4 tool calls, 48000 tokens, one output correction, 240 s). Evaluator checks unchanged, so the development and first held-out numbers compare directly with PLAN-0036.

The first held-out set is exposed: v4's audit-hook and abstention wording draws on PLAN-0036's review of it, so its result is comparison only. Qualification is decided only on the fresh held-out set: v4 is qualified for that scope only if every attempt passes every deterministic check with zero unknown tools and provider usage on every attempt, and independent review of the actual ready plans finds no defect that would make the authored test measure the wrong property (including `safe_behavior` contradicting `required_behavior` and witnesses for events the facility does not record). Anything less is reported as not qualified with failures attributed.

## Validation and progress

Base: main `334aa03`. `tests/agents/test_test_planning.py`: 33 passed (32 existing, 1 new). `make test-config`: 854 passed (853 on main plus 1).

## Decisions and next action

- Re-reads are handled structurally where that is exact (whole inventory returned) and by prompt otherwise; a per-window refusal would end the run under the shared zero tool-retry policy, and a short-circuit result would still spend the tool budget.
- The evaluator is not extended for `safe_behavior` consistency or witness truth; both stay review findings, so results remain comparable with PLAN-0036.

Next: freeze the fresh held-out set, then run development × v4 on RIG0.
