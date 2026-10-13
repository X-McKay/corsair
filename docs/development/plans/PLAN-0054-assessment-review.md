---
id: PLAN-0054
kind: plan
title: Evidence assessment comprehensive review and improvements
status: complete
updated: 2026-10-13
related: [SPEC-0050, SPEC-0030, SPEC-0035, HANDOFF-0074]
---

# Evidence assessment comprehensive review and improvements

## Objective and dependencies

Review active assessment prompts, skill, tools, contracts, evaluator and affected composition after PR47 at base 6be1b5f. Implement the concrete run-grounding gap independently on codex/agent-assessment-improvements. Runtime/CNI, witness envelope, dependency and real-provider qualification remain their existing gates.

## Steps

- [x] Verify source, contracts, historical records and frozen development baseline.
- [x] Require run-specific witness coverage and update skill/evaluator without changing datasets or shared runner.
- [x] Exercise partial and complete repeat coverage, incomplete baseline preservation and development comparison.
- [x] Review records and handoff; full offline guard result recorded below.

## Review findings and decisions

Prompt/skill: observed-data-only objective, hostile workload instruction treatment, exact safe behavior, candidate-only failures and separate sandbox observations are explicit. Clarified repeat citations and incomplete baseline preservation in v5. No broad prompt rewrite is justified by scripted evidence.

Tools/contracts: one bounded read_evidence port, zero tool retries, digest/unique inventory checks, numbered windows and successful current-run citation provenance are retained. No read_source, execution, filesystem, authority expansion or silent provider fallback is added. Operator-owned witness capture remains distinct from test-process claims.

Output/gates: finding and fix previously accepted any witness on each revision. A consistent repeat pair could receive an admitted conclusive proposal that cited run0 only. Fixed revision/run coverage for every typed witness-bearing run. Missing witness artifacts for an observed repeat are refused; incomplete witnessless baseline runs preserve earlier valid reproduction and the deterministic limitation. assess/admit dispositions and rejected-proposal retention are unchanged.

Evaluation: witness_grounded repeated the same per-revision gap, so required_reads could succeed while the conclusion lacked repeat citations. Fixed independently in the evaluator and added development-derived sensitivity tests. Existing frozen development cases lack a consistent multi-run conclusion; targeted variants exercise that gap without touching corpus or held-out manifest. Existing required_reads is item-level, not full-content semantic verification; citations prove provenance/coverage, not that model prose follows from every line. No claim of general semantic grounding is added. Native traces, usage, consistency and gate/oracle separation remain intact.

Composition: direct evidence items carry run indexes and are produced only for admitted witness records. Existing direct/durable factories reuse the same stage; no schema/adapter change. Full offline guards cover affected consumers; no native runtime rerun is justified for this bounded citation change.

## Validation and progress

Passed: targeted pytest assessment agent/evaluator suites, 31 checks (one existing event-loop deprecation warning). Candidate `make eval AGENT=assessment NOTE='Run-specific witness citations and evaluator sensitivity'`: 51/51 clean attempts, zero task failures, all ten assertion dimensions 51/51, same frozen development set and three repeats. Baseline `.runs/evals/assessment/20261013T094548Z-development-scripted` at v4: 51/51; candidate `.runs/evals/assessment/20261013T095555Z-development-scripted` at v5: 51/51. Dataset SHA256 b614014f07a638ca005243eade7f844b311ab09abc200dfe6c96bbea27baaa21 unchanged. Mean scripted requests 6, tool calls 5, input tokens 6105.294 and output tokens 179.882 unchanged; elapsed mean 0.024 to 0.025 seconds is a plumbing measurement, not model latency. Usage source scripted_estimate, no provider cost evidence.

Unrun: live provider candidate/baseline, native durable service/replay, OpenShell and real workloads. Root reported automatic approval review rejection of fixture export to the local provider; this lane made no live calls or workaround. Full `make test-config`:997 passed, one existing event-loop deprecation warning; includes affected direct composition and offline Temporal consumers. `git diff --check` passed. Raw receipts remain ignored under .runs/.

## Decisions and next action

Keep contract/tool/retry budgets unchanged (PR49 owns budgets). Root publishes the independent PR after inspecting this commit. Renew semantic/provider evidence only within authorized scope; do not relabel offline improvements as live qualification.
