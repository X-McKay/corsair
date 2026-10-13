---
id: IDEA-0009
kind: idea
title: Simple eval runner measurement and comparison improvements
status: proposed
updated: 2026-10-13
related: [IDEA-0008, SPEC-0044, PLAN-0048]
---

# Simple eval runner measurement and comparison improvements

## Problem and evidence

The objective is to understand and quantify agent success, accuracy, tokens and latency so development can follow measured evaluations. Extend the existing `make eval AGENT=<name>` loop and native Pydantic Evals reports; another evaluation framework is unnecessary.

Source reviewed at `7d04cf331bb279cc955139bf441d11eb42f1ffe8` and checked against publication base `59492d2`: `evals/run.py` already retains per-case assertions, clean attempts, observed efficiency means, coverage and baseline comparisons. However, `compare` returns before detailed tables when there is no reference; `summarize` does not aggregate failure telemetry; the comparison identity omits saved provider settings and concurrency; and baseline promotion writes a pointer without checking measurement completeness. A temporary synthetic exercise confirmed the first three behaviors; it was not a live performance measurement.

## Proposal and limits

1. **Useful standalone reports.** Always show current correctness, tokens and latency, even on the first run. Add comparison columns only when a reference exists. Keep operational completion, all-required-checks-passed, task correctness, expected abstention and unexpected blocking distinct. Use existing suite-specific assertions and reviewed expectations; do not relabel structural validity as accuracy. Show numerators, denominators and critical errors.
2. **Failure accounting.** Include available failed-attempt telemetry and attributable failure categories from existing reports/receipts. Show observed input/output token totals, per-attempt means and coverage; distinguish complete totals from partial observations. Show task duration and whole-run wall time, with mean/median/max and sample counts where supported. Missing measurements stay unknown, not zero. Show evaluator failures separately from agent/provider, dependency and runtime failures. Small samples do not support strong tail-latency claims; defer p95 reporting until its sample requirements are specified.
3. **Reliable comparisons.** Record a sanitized effective provider/model/settings identity, budgets, concurrency and evaluator identity alongside existing prompt/skill/tool and dataset identities. Include response caps, timeout and relevant thinking settings when available. Keep secrets and private endpoint values out of published summaries. Identify the intentionally changed variable and warn when changed cases, scoring or execution scope prevent a direct improvement claim. Preserve failure counts and measured coverage beside efficiency deltas.
4. **Better baseline checks.** Refuse missing, malformed or incomplete measurements as accepted reference baselines. A complete experiment containing failed attempts or low scores is still a valid before-change baseline if those outcomes and measurement coverage are recorded honestly. Do not require success to establish a baseline or silently discard failures. Keep scripted/live and structural/execution-backed references distinct. Optionally export a compact sanitized accepted summary and identities so reviewed evidence survives loss of ignored `.runs`; never commit raw private traces. No automatic promotion.
5. **Clear accuracy claims.** State whether results establish contract/structural behavior, live model behavior against fixtures, or actual execution correctness. Host authoring checks do not establish that generated tests run or discriminate vulnerable/fixed behavior. Compare bounded changes using frozen cases, settings and repeats; confirm improvements with independently prepared fresh held-out cases and relevant execution-backed checks. Once a held-out set has influenced tuning, treat it as development data for subsequent changes. Avoid exposing held-out labels through reports intended for tuning.

Reuse the existing CLI, native reports, receipts and comparison files. No dashboard, database, scheduler, generic scoring language, LLM judge or release-policy engine is proposed. Preserve security and execution boundaries; reporting changes do not require live inference or execution of generated code on the host.

## Decision

Proposed for consideration, not an implementation commitment. Start with useful standalone reporting and safe comparison identity; next cover failure telemetry and baseline validity. Use fixture-based reporting checks for a first run, a failed attempt, missing/partial usage, changed settings and complete low-scoring versus truncated baselines. Then run affected consumers. Continue the existing PLAN-0048 rather than creating a competing implementation plan, reconciling its historical progress with current source first.

[IDEA-0008](IDEA-0008-agent-release-policies.md) remains deferred until real baselines and recurring review decisions justify stable acceptance thresholds. These improvements should make the existing eval-driven loop easier to interpret without turning it into a release-governance system.
