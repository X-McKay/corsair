---
id: SPEC-0048
kind: spec
title: Environment host evaluation
status: draft
updated: 2026-10-13
related: [SPEC-0029, SPEC-0044, PLAN-0048]
---

# Environment host evaluation

## Goal and scope

Implement SPEC-0044 for environment with the production factory, frozen synthetic observations,
explicit-provider support and native Pydantic Evals. No setup command executes on the host.

## Boundaries and design

Fixtures answer SandboxExecution by exact argument vector; unexpected commands fail closed.
Operator tool budgets and unknown-delivery halt remain production behavior. The evaluator
checks status, layer, observed receipts, required source reads, command allowlist/order and budgets.
Dataset bytes are frozen by a SHA256 manifest. Outputs and usage are filed by the existing runner.
No provider fallback, scheduler, executor or runtime admission is introduced.

## Acceptance and validation

Eight cases repeat twice through make eval; affected contract tests and record guards pass.
Live mode is implemented but unrun. Synthetic receipt claims are never runtime qualification.

## Decisions and open questions

Reuse native Pydantic Evals and existing filing. Independent held-out semantics and captured
benchmark observations remain future work; no synthetic result admits runtime execution.
