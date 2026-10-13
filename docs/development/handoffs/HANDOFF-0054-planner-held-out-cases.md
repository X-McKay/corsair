---
id: HANDOFF-0054
kind: handoff
title: Planner held-out cases and live results
status: recorded
updated: 2026-10-13
related: [PLAN-0036, PLAN-0025, SPEC-0022]
---

# Planner held-out cases and live results

## Verified state

Branch `claude/planner-live-qualification-ktcy7w` from main `0d9bb5a` (PR #36); resolve the published commit with `git log -1 --format=%H -- docs/development/handoffs/HANDOFF-0054-planner-held-out-cases.md`. Delivered under [PLAN-0036](../plans/PLAN-0036-planner-live-qualification.md): six held-out test-planning cases in `evals/test_planning/cases-heldout.yaml` (frozen SHA256 `6159a676961106cbcdf3ee667669a5a57740fc9e0bf5b42c13b6ca5feeea2026`, independently reviewed before any provider run), evaluator options `--cases` and `--repeat`, provider configuration in `configuration.json`, and a heuristic `scratch` check on fixture setup. The planning prompt and contracts are unchanged. The planner is not qualified and not connected.

## Validation and blockers

`make test-config`: 785 passed (one existing deprecation warning), including the SPEC-0023 held-out manifest guard. Scripted held-out plumbing: 12/12 attempts pass every check. Live runs on RIG0 against llm.almckay.io (8192 response cap, 2048 thinking budget), each once: held-out v2 12/18 and v3 12/18 passed every check; development v3 4/12, with every completed ready plan writing a fixture to `tmp_path.parent`. Failures are attributed in PLAN-0036: re-read budget exhaustion, reads of the planned test path, scratch escapes, wrong ready status on unobservable concerns, and semantic defects review found in passing plans. Not qualified under either prompt. No Temporal or OpenShell check ran; the kind cluster was not used.

## Decisions and next steps

The scratch finding stays an evaluator check because a typed field would change the prompt version that PR #34 owns. Next: the planning prompt owner addresses the PLAN-0036 prompt findings (unreadable planned test paths, scratch example, consistent `safe_behavior`, abstention under v3); measure on the development set, then on this held-out set once, then on fresh held-out cases before claiming qualification.

## Continuation prompt

```text
Read AGENTS.md, docs/development/CURRENT.md, PLAN-0036 and this handoff. Address the PLAN-0036 prompt findings in the planning skill (new prompt version), run the development set on RIG0 with --cases development, then --cases heldout once; retain every attempt and review every plan. Freeze fresh held-out cases before any qualification claim. Run make test-config, update CURRENT.md and write a new handoff.
```
