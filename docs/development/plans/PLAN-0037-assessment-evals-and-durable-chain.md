---
id: PLAN-0037
kind: plan
title: Assessment and chain evaluation sets with durable chain mode
status: in_progress
updated: 2026-10-13
related: [SPEC-0035, SPEC-0030, SPEC-0031, PLAN-0029, PLAN-0031, IDEA-0004]
---

# Assessment and chain evaluation sets with durable chain mode

## Objective and dependencies

Implement [SPEC-0035](../specs/SPEC-0035-assessment-evals-and-durable-chain.md) from main `0d9bb5a`. Independent of the kind cluster (reserved by PLAN-0034 and PLAN-0033). Rebase expected after PRs #35 (witness capture, touches `composition/`), #34 (assessment output function and prompts) and #33 (fixture runner) land.

## Steps

- [ ] Assessment dataset builder, cases, evaluators, scripted run and guards.
- [ ] Chain dataset over the reviewed pair variants, direct mode.
- [ ] `run_chain` routing split; `run_direct` unchanged for callers.
- [ ] Durable chain: child stage workflows, revision activity, worker-side runner resolution, native Temporal tests and replay.
- [ ] Chain dataset in durable mode; direct/durable parity.
- [ ] Live baselines on the local provider (assessment development split; chain with live stages).
- [ ] Review, records, handoff.

## Validation and progress

None yet.

## Decisions and next action

Work proceeds in parallel: the evaluation sets and the durable chain touch separate files except `composition/direct.py`, which only the durable work changes, keeping `run_direct`'s signature.
