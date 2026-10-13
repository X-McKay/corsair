---
id: PLAN-0053
kind: plan
title: Authoring review and structural evaluation
status: complete
updated: 2026-10-13
related: [SPEC-0028, SPEC-0044, PLAN-0053, SPEC-0049, ISSUE-0006]
---

# Authoring review and structural evaluation

## Objective and dependencies

Comprehensively review authoring at base `6be1b5f` and implement the bounded evaluator corrections in [SPEC-0049](../specs/SPEC-0049-authoring-structural-evaluation.md). Existing runtime gates and ISSUE-0006 remain outside this host-only work. PR49 is independent, unmerged witness-admission/prompt/budget work.

## Steps

- [x] Review contracts, native factory, prompt, eager skill, tools, static checker, host runner, evaluator, frozen cases and linked SPEC-0028/PLAN-0027/HANDOFF-0045/PLAN-0048.
- [x] Fix reproducible false positives and add meaningful negative/positive regressions.
- [x] Compare unchanged frozen scripted cases with the base run; run affected tests and offline guards.
- [x] Review final diff with corsair-review; update CURRENT and handoff.

## Validation and progress

Baseline root-owned `make eval AGENT=authoring`: 12/12 at `.runs/evals/authoring/20261013T094548Z-development-scripted`, prompt v5/config v2, frozen dataset digest `73be36ab7633d47c42b6df2d82c1963457639d0166d3d0e0443d09f9dfa02444`. Candidate `.runs/evals/authoring/20261013T095145Z-development-scripted`, same command/set: 12/12; affected pytest suites: 106 passed, one existing pydantic_graph event-loop deprecation warning. Candidate receipts retain native spans and scripted usage estimates; these are not provider measurements. Baseline checker sources independently reproduce all four invalid facts as True (deferred target, process call, deferred literal and deferred assertion); candidate regressions reject them. `make test-config`:1052 passed, one existing warning, 50.84 seconds. `git diff --check` initially found trailing whitespace in the expanded set; corrected and rechecked. Live comparison remains unrun after parent coordination: automatic approval review rejected the proposed provider boundary; parent handles explanation and any approval. Mean scripted metrics before/after: 5.667 requests, 4.667 tool calls, 1.5 dev runs, 3079 input/1049.167 output token estimates; elapsed 0.027/0.026 seconds (not a live performance qualification).

## Comprehensive review and decisions

- Prompt/skill: clear sole objective, exact pair, grounded source reads, explicit approved writes, bounded corrections and withheld security outcome. No measured reason to edit wording in this lane; preserve v5/config v2 and skill hash. PR49's independent v6/witness gate must receive its own comparison.
- Contracts/finalizer: grounded excerpts, immutable typed inputs, patch reconstructed from current-run successful writes, digest/operation matching, final run coverage, exact discovery, passing control, security setup/skip refusal and assertion-line membership. Structural line membership cannot establish assertion intent.
- Tools: narrow native Capability toolsets, explicit model seam, zero tool retries, bounded writes/runs, sequential run dispatch and operation identity, historical messages grant no authority. No new scheduler, wrapper or mutable dependency state needed.
- Evals: six development cases/two repeats, injected setup errors and host static double, native trajectory/budget/span metrics and evaluator-only oracles. Reproduced deferred target false-positive and incomplete os process families; fixed plus deferred input/assertion consistency. Keep whole-file mock/skip/process scanning conservative. Static collection does not emulate decorators, parametrization, plugins or actual import execution; honest simulated execution is retained.
- Remaining limits: no authoring held-out set; no live-provider lane run here; no generated-code execution, sandbox replay, durable or OpenShell qualification. All structural facts still permit dead branches, binding spoofing and semantically irrelevant asserts; reject any claim that these fixes prove test correctness. Hold live security qualification until independent sandbox replay and witness evidence admit it.

## Decisions and next action

Review and merge this independent evaluator PR, then reconcile PR49 without copying unmerged changes. Authoring held-out creation and sandbox replay remain PLAN-0048 follow-ups; do not inspect hidden sets during prompt iteration. Existing authorization covers commits; parent owns publication.
