---
id: PLAN-0107
kind: plan
title: Dead-code review, focused functions, Ruff and ty
status: complete
updated: 2026-10-25
related: [PLAN-0106]
---

> Historical record. Commands, counts and status describe the recorded revision, not the current working tree. See [current work](../../README.md) for current guidance.

# Dead-code review, focused functions, Ruff and ty

Review the existing Plan 1 implementation without expanding recipe, provider or orchestration scope. Remove confirmed dead/stale helpers, arguments and configuration; retain SDK callbacks, Pydantic validators, wire-schema fields and forbidden-label enums that static scans cannot recognize as live contracts.

Pin ty alongside Ruff and add warning-failing full-project typing to `make check`, already used by CI. No broad diagnostic ignores or runtime/test source exclusions. Frozen target inputs must retain source digests and line numbers, so Ruff does not rewrite `evals/fixtures`; ty and canonical-hash conformance still cover them.

Refactor the monolithic CLI dispatcher into explicit single-command handlers. Use one shared lexical request loader, one safe validation-error formatter, one unknown-aware usage aggregate and focused isolated-evaluator functions. Preserve native ADK/Temporal/Docker ownership, oracle isolation, logging privacy, immutable side-effect reconciliation and cancellation cleanup. Avoid speculative mixins/ports/registries; small explicit composition is the simpler pattern for the actual consumers.

Validate unit tests, true Docker/Temporal/CLI composition, history replay, fresh installed-wheel resources and a post-refactor frozen live-auditor evaluation. Do not retry or evade the provider-policy-blocked security producer. Record exact receipts and microbenchmark boundaries before marking complete.

Completed: Ruff/ty pass; strict full suite 105 passed in 110.07 seconds; frozen live-auditor evaluation 6/6 passed. See [HANDOFF-0140](../handoffs/HANDOFF-0140-code-quality.md).
