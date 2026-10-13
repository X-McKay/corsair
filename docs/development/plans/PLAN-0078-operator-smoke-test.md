---
id: PLAN-0078
kind: plan
title: Operator smoke test as the environment baseline for projects with no tests
status: in_progress
updated: 2026-10-13
related: [SPEC-0071, SPEC-0069, PLAN-0076, PLAN-0073]
---

# Operator smoke test as the environment baseline for projects with no tests

## Objective and dependencies

Implement [SPEC-0071](../specs/SPEC-0071-operator-smoke-test.md) offline on top of SPEC-0069 (runtime inference). The `Preparation.prepare` overlay keyword was agreed with the chain thread (its OpenShell adapter uploads the overlay with the capture). The case command and per-case result line come from the Node thread's entry-point PR; the `corpus-python` cohort list is here.

## Steps

- [x] `SmokeTest` contract; templates as `smoke` data on the framework rows of `deploy/runtime-matrix.yaml` (Al 17:08Z: general across languages, nothing baked into images), carried on `RuntimeOutcome.smoke_tests`; `EnvironmentInput.smoke_tests`, trusted `baseline_basis`, skill line, prompt `environment-v7-operator-smoke-test`.
- [x] Chain: offer from the selection, overlay through `Preparation.prepare`, smoke file into planning/authoring inventory, limitation.
- [x] `evals/corpus/cohorts.json`: `corpus-python`, the 17 Python development cases.
- [x] `evals/corpus/issues.py`: each corpus case as an issue JSON (`corsair-issue-request/v1`, per the kick-off note) over a local bare repository (each variant one root commit, fixed neutral metadata, reproducible ids) plus an evaluator-only `expected.json`; `--set corpus-python` writes the cohort; the 17 cases are committed under `evals/corpus/issues/` (repository named by its checkout-relative path, so a clone carries the case data), and a test checks they match the generator.
- [ ] Run the Jest and JUnit templates in their images (image-only harness).
- [ ] Live environment eval against its baseline when the model is free.
- [ ] Wire `SET=corpus-python` into the chain suite once the issue entry point (`corsair investigate --issue-json`, Node thread) lands; align field names with its schema.

## Validation and progress

2026-10-13: `tests/unit/test_environment_smoke.py` (templates against the admission table; Python, Perl and Ruby templates pass natively on the host), `tests/agents/test_chain_environment_stage.py` (smoke baseline reaches the gates; wrong id on the smoke path refused; overlay offered). `make eval AGENT=environment` scripted 16/16.

## Decisions and next action

- Smoke file written up front with the capture, chosen by the agent only when no project test runs, recorded in `baseline_basis` (agreed with the chain thread's adapter shape).
- Next: issue JSON per corpus case for the Node thread's issue entry point, then the cohort set wiring; the smoke test stays in the environment stage, not the case file.
