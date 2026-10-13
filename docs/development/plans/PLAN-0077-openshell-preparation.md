---
id: PLAN-0077
kind: plan
title: OpenShell preparation for the chain's environment stage
status: in_progress
updated: 2026-10-13
related: [SPEC-0070, SPEC-0068, PLAN-0075]
---

# OpenShell preparation for the chain's environment stage

## Objective and dependencies

Implement [SPEC-0070](../specs/SPEC-0070-openshell-preparation.md) after #106. Depends on merged work: SPEC-0068 and PLAN-0075 (#100, #103), SPEC-0032 `OpenShellTestWorkspace`, SPEC-0026 `phase_policy`. Merging needs one live gate on a fresh RIG0 cluster, because this is a sandbox and policy change.

## Steps

- [x] `PolicyReceipt`/`SandboxPolicy` port and `CliPolicy`; scripted stand-in tests.
- [x] `OpenShellTestWorkspace.prepare_source`/`release_source` (the same placement and verification, no test files).
- [x] `OpenShellPreparation` with `PreparationRefused` and `sweep`; the stage records no cleanup for a refusal before any sandbox.
- [x] Live gate `make qualify-environment-preparation`.
- [ ] `make test-config`, evals, CURRENT.md row, PR; live gate on RIG0; handoff (HANDOFF-0100).

## Validation and progress

- 2026-10-13: Python toolchain image is the official slim image with no `git`, so in-sandbox fetch cannot run; card to Al recommends the qualified upload route, adapter written that way. The gate test collects; it has not run.

## Decisions and next action

Upload route first; the run records cleanup unconfirmed after a lost worker and the operator sweeps. Next: the PR after #106 merges, then Al's paste of the gate on RIG0.
