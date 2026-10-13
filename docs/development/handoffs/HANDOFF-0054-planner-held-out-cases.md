---
id: HANDOFF-0054
kind: handoff
title: Planner held-out cases and live runs started
status: recorded
updated: 2026-10-13
related: [PLAN-0036, PLAN-0025, SPEC-0022]
---

# Planner held-out cases and live runs started

## Verified state

Branch `claude/planner-live-qualification-ktcy7w` from main `0d9bb5a` (PR #36); resolve the published commit with `git log -1 --format=%H -- docs/development/handoffs/HANDOFF-0054-planner-held-out-cases.md`. Delivered under [PLAN-0036](../plans/PLAN-0036-planner-live-qualification.md): six held-out test-planning cases in `evals/test_planning/cases-heldout.yaml` (frozen SHA256 `6159a676961106cbcdf3ee667669a5a57740fc9e0bf5b42c13b6ca5feeea2026`, independently reviewed before any provider run), evaluator options `--cases` and `--repeat`, provider configuration in `configuration.json`, and a heuristic `scratch` check on fixture setup. The planning prompt and contracts are unchanged. The planner is not qualified and not connected.

## Validation and blockers

`make test-config`: 785 passed (one existing deprecation warning), including the SPEC-0023 held-out manifest guard. Scripted held-out plumbing: 12/12 attempts pass every check. Live runs (held-out × prompt v2 and v3, three repeats each; development × v3, two repeats) were started on RIG0 against llm.almckay.io with an 8192 response cap and 2048 thinking budget; results were not available when this PR was prepared for merge at the user's request. No Temporal or OpenShell check ran; the kind cluster was not used.

## Decisions and next steps

The scratch finding stays an evaluator check because a typed field would change the prompt version that PR #34 owns. Next: record the runs per prompt version without rerunning failures, review every ready plan, apply the PLAN-0036 criteria, and relay any prompt change to the #34 owner.

## Continuation prompt

```text
Read AGENTS.md, docs/development/CURRENT.md, PLAN-0036 and this handoff. On RIG0, read .runs/planner-qual-20261013/ (summary-*.json, report-*.json; worktrees /home/al/git/corsair-planner-v2 and -v3). Record each run's results in PLAN-0036 against its prompt version, review every ready plan independently, and apply the pre-registered criteria; do not rerun failed attempts. Do not edit the planning prompt; relay prompt findings to its owner. Run make test-config, update CURRENT.md and write a new handoff.
```
