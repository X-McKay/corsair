---
id: PLAN-0036
kind: plan
title: Test planner live qualification on held-out cases
status: in_progress
updated: 2026-10-13
related: [PLAN-0025, SPEC-0022, PLAN-0031, SPEC-0023, ISSUE-0007]
---

# Test planner live qualification on held-out cases

## Objective and dependencies

Decide whether the isolated SPEC-0022 planner is qualified on cases it was not developed on, following the PLAN-0025 next action: freeze fresh held-out cases before any further comparison, and respond to the `tmp_path.parent` scratch finding. Measure the prompt on main (`test-planning-v2`) and the prompt in draft PR #34 (`test-planning-v3`, PLAN-0035 on that branch) under one provider profile, so the prompt is the only variable. This plan does not edit the planning prompt or contracts (PR #34 owns the prompt), connect the planner to another stage, or touch the kind cluster. Inference uses the local model at llm.almckay.io from RIG0.

## Steps

- [x] Add six held-out cases (`evals/test_planning/cases-heldout.yaml`): four ready (shell command injection, guarded tar extraction, SQL string formatting, unsafe unpickling with hostile instructions in application source) and two unsupported (markup injection with no executed baseline test, timing side channel with no timing facility). Different vulnerability classes, symbols and files from the development set; same Python/pytest toolchain as the only admitted one.
- [x] Evaluator: `--cases {development,heldout}`, `--repeat`, provider configuration recorded in `configuration.json`, and a `scratch` check on fixture setup (names `.parent` or a fixed host directory). Offline tests: held-out scripted plumbing passes, sets are disjoint, the scratch check refuses the reviewed escape shapes.
- [x] Independent review of the held-out cases and markers before any provider run; then freeze.
- [ ] Live runs on RIG0, sequential, no retries: held-out × v2 (3 repeats), held-out × v3 (3 repeats), development × v3 (2 repeats, for comparison with live002). Started 2026-10-13 from detached worktrees `/home/al/git/corsair-planner-v2` (`f8d3d5c`) and `/home/al/git/corsair-planner-v3` (`f8d3d5c` locally merged with PR #34 head `a2393e2`); evidence under `.runs/planner-qual-20261013/` (git-ignored). Results not yet recorded when this PR merged at the user's request; they follow in a separate change.
- [ ] Independent review of every actual ready plan; attribute each failure.
- [x] Records, `CURRENT.md`, handoff (HANDOFF-0054) for the offline deliverable; live results to follow.

## Pre-registered criteria

Provider profile for every run: the saved RIG0 provider configuration with `response_token_limit` 8192 and `thinking_token_budget` 2048 (the planning profile in PR #34's `stage-profiles.json`, and live002's). Budgets unchanged from PLAN-0025 (5 requests, 4 tool calls, 48000 tokens, one output correction, 240 s).

A prompt version is qualified for this held-out scope only if all 18 held-out attempts pass every deterministic check (including `scratch`), with zero unknown tools and provider usage on every attempt, and independent review of the actual ready plans finds no defect that would make the authored test measure the wrong property. Anything less is reported as not qualified with the failures attributed (budget, abstention, oracle, scratch, authority, grounding). The development-set run is comparison only and qualifies nothing.

## Validation and progress

Base: main `0d9bb5a`. `tests/agents/test_test_planning.py`: 31 passed (29 existing, 2 new). `make test-config`: 783 passed (781 on main plus 2).

Held-out review (independent Opus reviewer, before any provider run): line numbers and statuses confirmed; no oracle or case-name leakage into agent inputs. Blocking: the unpickling reference witness named `os.getcwd`, but on Linux the `pickle.find_class` audit event records `('posix', 'getcwd')` and a plain dict load records none (reproduced locally); both witnesses were corrected. Marker fairness fixes: the command-injection markers `;`/`|` and the unpickling markers `reduce`/`global`/`eval`/`exec` could appear in correct control prose and were replaced; SQL markers gained lowercase payload shapes; the `-x` and bare `not vulnerable` forbidden markers were dropped as false-positive risks (the contract already enforces discovery tokens). The unused `hmac` route was removed from the timing case. Recorded caveats: `archive_extraction_guarded` is a near-transfer of the development guarded traversal case (same `../` marker, `open` witness, guard preservation), and the two unsupported cases transfer development rules (no baseline, missing facility) to new code; a `ready` timing plan that spies on a constant-time comparison is a defensible alternative but checks a fix mechanism with an unlisted facility. Frozen held-out SHA256: `6159a676961106cbcdf3ee667669a5a57740fc9e0bf5b42c13b6ca5feeea2026`.

## Decisions and next action

- The scratch finding is handled as an evaluator check, not a contract change: a typed scratch-relative field would change the output schema the model sees, which is part of the prompt version PR #34 owns. The check is a heuristic anchor over prose; review remains mandatory.
- Held-out cases stay Python/pytest because that is the only admitted toolchain; generality across languages is not claimed.

Next: record the three live runs exactly as they ended (per prompt version), review every actual ready plan independently, and decide qualification against the pre-registered criteria. Any prompt change the results call for goes to the PR #34 owner, not into this plan. The planner stays disconnected from other stages until it and identification are admitted. No qualification is claimed by this plan so far.
