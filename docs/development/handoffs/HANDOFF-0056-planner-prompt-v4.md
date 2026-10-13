---
id: HANDOFF-0056
kind: handoff
title: Planner prompts v4 to v6, read guard and a fresh held-out set
status: recorded
updated: 2026-10-13
related: [PLAN-0038, PLAN-0036, SPEC-0022, SPEC-0023]
---

# Planner prompts v4 to v6, read guard and a fresh held-out set

## Verified state

Branch `claude/planner-prompt-v4-mbwx5t` (draft PR #38) from main `334aa03`. Delivered: planning prompt `test-planning-v6` (skill and rendered prompt; v4 and v5 were development iterations recorded in PLAN-0038), config `test-planning-config-v2` (native `FunctionToolset.prepared` withdraws `read_source` once every inventory line was returned in the run), a second held-out set `evals/test_planning/cases-heldout-2.yaml` frozen by manifest (SHA256 `7daba5a5…484e`), evaluator `--cases heldout2`. The shared source reader and every other stage are unchanged. The planner is not qualified and stays disconnected.

## Validation and blockers

`make test-config` 854 passed at `5ed852b` (853 on main plus 1); `tests/configuration` and `tests/agents/test_test_planning.py` 132 passed after the held-out freeze. Live on RIG0 (`/home/al/git/corsair-pr38`, evidence `.runs/planner-v4-20261013/`, git-ignored; local model, 8192 cap, 2048 thinking), each run once: development v4 12/12, v5 11/12, v6 12/12; v6 fresh held-out 13/18, v6 first (exposed) held-out 15/18 with one error. Mechanical failures (re-reads, unlisted reads, length cap) did not occur in any of the 60 live attempts. Blocker: semantic defects on held-out plans (wrong status on one case 3/3, witnesses the facility contradicts, outcome forecasts, development identifiers carried over, harmful payloads), attributed in PLAN-0038. The kind cluster was not used.

## Decisions and next steps

The fresh held-out set is exposed to v6; a further candidate needs a third set written and reviewed apart from its author. Al chooses between a typed witness contract (drafted as SPEC-0040, design only) and continuing the chain with the planner unqualified behind the disposition gates. The authoring stage reads its to-be-created test path in live chain runs (PLAN-0039); its prompt owner should apply the planner's approved-path wording or a typed refusal.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then PLAN-0038, PLAN-0036, SPEC-0022, SPEC-0023 and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. If the user chose the typed witness contract: draft a spec for a witness field naming a listed facility, event kind and expected path or argument with a harmless sentinel effect, add a deterministic check against the environment's facility list, measure on development cases first, then have agents other than the prompt author write and review a third held-out set and freeze it before one live run. Never name held-out cases in records. Run make test-config, preserve live evidence under .runs/, update PLAN, CURRENT.md and write a new handoff.
```
