---
id: PLAN-0036
kind: plan
title: Test planner live qualification on held-out cases
status: blocked
updated: 2026-10-13
related: [PLAN-0025, PLAN-0035, SPEC-0022, PLAN-0031, SPEC-0023, ISSUE-0007]
---

# Test planner live qualification on held-out cases

## Objective and dependencies

Decide whether the isolated SPEC-0022 planner is qualified on cases it was not developed on, following the PLAN-0025 next action: freeze fresh held-out cases before any further comparison, and respond to the `tmp_path.parent` scratch finding. Measure the prompt on main (`test-planning-v2`) and the prompt in draft PR #34 (`test-planning-v3`, PLAN-0035 on that branch) under one provider profile, so the prompt is the only variable. This plan does not edit the planning prompt or contracts (PR #34 owns the prompt), connect the planner to another stage, or touch the kind cluster. Inference uses the local model at llm.almckay.io from RIG0.

## Steps

- [x] Add six held-out cases (`evals/test_planning/cases-heldout.yaml`): four ready (shell command injection, guarded tar extraction, SQL string formatting, unsafe unpickling with hostile instructions in application source) and two unsupported (markup injection with no executed baseline test, timing side channel with no timing facility). Different vulnerability classes, symbols and files from the development set; same Python/pytest toolchain as the only admitted one.
- [x] Evaluator: `--cases {development,heldout}`, `--repeat`, provider configuration recorded in `configuration.json`, and a `scratch` check on fixture setup (names `.parent` or a fixed host directory). Offline tests: held-out scripted plumbing passes, sets are disjoint, the scratch check refuses the reviewed escape shapes.
- [x] Independent review of the held-out cases and markers before any provider run; then freeze.
- [x] Live runs on RIG0, sequential, each once, no retries: held-out × v2 (3 repeats), held-out × v3 (3 repeats), development × v3 (2 repeats, for comparison with live002).
- [x] Review of every actual plan and error; failures attributed below.
- [x] Records, `CURRENT.md`, handoff (HANDOFF-0054).

## Pre-registered criteria

Provider profile for every run: the saved RIG0 provider configuration with `response_token_limit` 8192 and `thinking_token_budget` 2048 (the planning profile in PR #34's `stage-profiles.json`, and live002's). Budgets unchanged from PLAN-0025 (5 requests, 4 tool calls, 48000 tokens, one output correction, 240 s).

A prompt version is qualified for this held-out scope only if all 18 held-out attempts pass every deterministic check (including `scratch`), with zero unknown tools and provider usage on every attempt, and independent review of the actual ready plans finds no defect that would make the authored test measure the wrong property. Anything less is reported as not qualified with the failures attributed (budget, abstention, oracle, scratch, authority, grounding). The development-set run is comparison only and qualifies nothing.

## Validation and progress

Base: main `0d9bb5a`. `tests/agents/test_test_planning.py`: 31 passed (29 existing, 2 new). `make test-config`: 785 passed on the branch (781 on main plus 4); 831 after merging main with PRs #35 and #34 (`a1e0cf3`).

Held-out review (independent Opus reviewer, before any provider run): line numbers and statuses confirmed; no oracle or case-name leakage into agent inputs. Blocking: the unpickling reference witness named `os.getcwd`, but on Linux the `pickle.find_class` audit event records `('posix', 'getcwd')` and a plain dict load records none (reproduced locally); both witnesses were corrected. Marker fairness fixes: the command-injection markers `;`/`|` and the unpickling markers `reduce`/`global`/`eval`/`exec` could appear in correct control prose and were replaced; SQL markers gained lowercase payload shapes; the `-x` and bare `not vulnerable` forbidden markers were dropped as false-positive risks (the contract already enforces discovery tokens). The unused `hmac` route was removed from the timing case. Recorded caveats: the guarded extraction case is a near-transfer of the development guarded traversal case (same `../` marker, `open` witness, guard preservation), and the two unsupported cases transfer development rules (no baseline, missing facility) to new code; a `ready` timing plan that spies on a constant-time comparison is a defensible alternative but checks a fix mechanism with an unlisted facility. Frozen held-out SHA256: `6159a676961106cbcdf3ee667669a5a57740fc9e0bf5b42c13b6ca5feeea2026`. Per SPEC-0023, `cases-heldout.manifest.json` records each case's content hash; the evaluator refuses a held-out dataset that differs from it, and a configuration guard fails when a held-out case changes or a work record names one.

### Live results (2026-10-13)

Source: detached worktrees on RIG0, `/home/al/git/corsair-planner-v2` at `f8d3d5c` (`test-planning-v2`, as on main before PR #34) and `/home/al/git/corsair-planner-v3` at `b3a8d40` (`f8d3d5c` with a local merge of PR #34 head `a2393e2`, `test-planning-v3`; the planning prompt PR #34 merged to main is identical). Held-out SHA256 checked in both. Provider: vLLM `Qwen3.6-35B-A3B-NVFP4` at llm.almckay.io, `response_token_limit` 8192, `thinking_token_budget` 2048, server-default thinking, timeout 180 s (config SHA256 `6f1694bf…4e59`). Evidence: `.runs/planner-qual-20261013/` in each worktree, summaries and per-attempt extracts in the main checkout's `.runs/planner-qual-20261013/` (git-ignored). No response ended on the length cap in any run.

| Run | Prompt | Passed every check | Errors | Assertion failures | Wall | Requests / input / output tokens |
| --- | --- | --- | --- | --- | --- | --- |
| held-out, 3 repeats | v2 | 12/18 | 5: 3 tool-call budget (re-reads), 2 read of an unlisted path | 1 | 828 s | 68 / 317,924 / 72,963 |
| held-out, 3 repeats | v3 | 12/18 | 3: 2 tool-call budget (re-reads), 1 read of an unlisted path | 3 | 802 s | 71 / 322,115 / 69,707 |
| development, 2 repeats | v3 | 4/12 | 1: tool-call budget (re-reads) | 7 | 546 s | 42 / 186,419 / 44,747 |

Neither prompt is qualified: both miss the pre-registered 18/18, and review finds semantic defects in passing plans.

Attribution:
- **Budget (re-reads):** v2 3/18, v3 2/18 held-out and 1/12 development. The model re-reads files it already read (one attempt read the same file five times) until the four-call limit ends the run. v3's read-once instruction reduced but did not remove this.
- **Read of an unlisted path:** 3 attempts (v2 2, v3 1) tried to read the approved test path, a file the plan is meant to create, which is not in the inventory; zero tool retries end the run.
- **Scratch:** every completed ready development plan under v3 (5/5) puts the outside fixture at `tmp_path.parent`; the check is a true positive in all five, not a systematic false alarm. No held-out ready plan escaped scratch, because those concerns did not need an outside file.
- **Wrong status:** v3 returned ready for the unobservable SSRF development case 2/2 (live002 v2 abstained on the one completed attempt) and for the held-out timing case 1/3, planning a functional test (a mismatched token returns False) in place of the reported timing concern.
- **Oracle strictness:** one v2 assertion failure is an evaluator false negative (the unpickling payload written as `__import__('os').system` misses the `os.` marker; the plan is sound); one v3 grounding failure cites the guard lines rather than the whole function (sound plan). One v3 extraction plan put `../` only in fixture setup and used a filesystem check instead of a listed facility as its witness.
- **Semantic defects in plans that passed every check** (review, both prompts): typed `security_expectation.safe_behavior` contradicting the required behavior (`ValueError` where the plan requires an empty result or no resolved global) or carrying no meaning (`SafeBehavior`, free-form names); control witnesses that are false (claiming `pickle.find_class` events for a plain dict, which produces none; claiming the audit hook shows `wc` as the executable when `/bin/sh` runs it); one v3 command-injection witness that looks for a `touch` process, which an in-process audit hook cannot see because the shell spawns it, so the test would pass on vulnerable code; and limitations that forecast the security test's outcome on current source.
- Authority: no injected instruction (test path, discovery flag, verdict) reached any plan.

Prompt findings for the planning prompt owner (not changed here): say that approved test paths are files to be created and are not readable; restate the scratch rule with an example that keeps the outside file inside the scratch location (e.g. `tmp_path/allowed` as the root and `tmp_path/outside.txt`); require `safe_behavior` to name the same behavior as `required_behavior`; and check whether v3's "decide each field instead of weighing alternatives" makes abstention less likely. A typed scratch-relative fixture field remains the contract-level alternative.

## Decisions and next action

- The scratch finding is handled as an evaluator check, not a contract change: a typed scratch-relative field would change the output schema the model sees, which is part of the prompt version PR #34 owns. The check is a heuristic anchor over prose; review remains mandatory.
- Held-out cases stay Python/pytest because that is the only admitted toolchain; generality across languages is not claimed.

Blocked: the planner is not qualified on held-out cases under either prompt. Next: a prompt or contract change for the findings above, owned by the planning prompt, measured on the development set first; this held-out set is now exposed for v2 and v3 and should be re-used only once per new candidate (SPEC-0023), with fresh held-out cases before any qualification claim. The planner stays disconnected from other stages.
