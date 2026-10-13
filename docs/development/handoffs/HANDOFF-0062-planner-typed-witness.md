---
id: HANDOFF-0062
kind: handoff
title: Planner typed witness and third held-out run
status: recorded
updated: 2026-10-13
related: [SPEC-0040, PLAN-0044, PLAN-0038, SPEC-0022, SPEC-0033]
---

# Planner typed witness and third held-out run

## Verified state

Branch `claude/planner-typed-witness-abcjvt`, PR #44 against `main` (main merged in through #38, #43, #41 and #40). Delivered: SPEC-0040 contract (`WitnessFacility`, `PlannedWitness`), deterministic admission in the planner output function (listed facility and kind, expectations, scratch-relative canonical `file_open` subjects, distinct subjects, security subject named in the security input or fixture, `safe_behavior` rule, and a ready plan refused without an executed baseline test), prompt `test-planning-v7`, evaluator `typed_witness`, the two earlier held-out sets retired, a third held-out set (`--cases heldout3`) written and independently reviewed by agents other than the prompt author and the runner, frozen by manifest. Composition requests the operator witness envelope only when the plan's security witness is a `file_open` whose subject is exactly the envelope's file (review findings on #44); otherwise the run has no witness and stays inconclusive. A planned `no_file_open` safe behavior is matched by an attributed absence on the candidate only; planned-file opens on other threads make the effect `unknown` (probe `offstack_planned`; SPEC-0033 and SPEC-0040 updated). Not implemented: a witness request built from the plan, and control calibration.

## Validation and blockers

`make test-config` passes on the latest head (count in PLAN-0044 and the PR); each #44 review finding (unbound kinds, aliases, directory-prefixed subjects, unconsumed `no_file_open`, off-thread opens, substring identifiers) has a regression that fails on the head before its fix. Live on RIG0 (worktree `/home/al/git/corsair/.worktrees/planner-typed-witness-abcjvt`, evidence `/home/al/git/corsair/.runs/typed-witness-*-20261013/`, git-ignored; provider file `.runs/corsair-pr38/planner-v4-20261013/planner-provider.json`, 8192 cap, 2048 thinking, 180 s), each once, no retries: development v7 11/12 (one earlier run with the 16384 profile by mistake, 10/12, kept as a record); development v7 + baseline admission 11/12; third held-out 17/18, zero unknown tools, usage on every attempt. Independent review: statuses all correct; one vacuous witness from a payload resolved outside scratch; prose defects (invented exception types 3, outcome forecasts 3, unprefixed test ids 2, carried-over development identifiers 2, one inert markup payload, one unconstructed object). Not qualified (PLAN-0044). The kind cluster was not used.

## Decisions and next steps

The third held-out set is exposed. Next bounded actions: build the plan-derived witness request and control calibration (SPEC-0040); add deterministic checks for the recurring prose defects (test id prefix and baseline-name collision, exception type only when required, scratch-anchored adversarial paths, a correction message that keeps citations). A further planner candidate needs a fourth held-out set written apart from its author.

Merge decision (Al, 2026-10-13 12:16Z, "Lets merge both of these"): #44 merges to main unqualified, without further live inference. The plan-based witness binding, the four text-defect checks above and a fourth held-out set move to a follow-up. Until that follow-up runs, the planner on main is unqualified at development 11/12 and held-out 17/18. Merging main brought in the planner's grounding admission (target-anchor coverage, identifier-boundary implementation calls), so the merged prompt is `test-planning-v7-grounding-3` with `test-planning-config-v5`; that combination has offline checks only and no live run, so the 11/12 and 17/18 results above are for `test-planning-v7`. Also for the follow-up: a regression that pins the candidate-only `no_file_open` mapping, and the SPEC-0033 limits for a lazy reader and an unjoined worker thread.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then SPEC-0040, PLAN-0044 and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. Implement the SPEC-0040 plan-derived WitnessRequest and control calibration in direct (and durable) composition, keeping the interim envelope refusal until the plan binding is admitted. Do not run held-out sets 1-3 as qualification; they are exposed. Run make test-config and the fixture composition tests, preserve evidence, update work records/CURRENT.md, and write a new handoff.
```
