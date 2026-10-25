# Current work

The `manus/re-design` branch is a from-scratch Google ADK + Temporal rebuild, authorized on 2026-10-24. It implements the recommended durable-round Plan 1. The layout follows the user's linked agent-playbook reference architecture. The previous v2 source, corpus, OpenShell stack and records remain accessible in Git history at base `d3da7d3f`; they are not executable compatibility paths in this branch.

Canonical behavior is described in [README](../../README.md), [architecture and ownership](../architecture.md), [risk assessment](../../src/corsair/runtime/risk.md), and [PLAN-0105](plans/PLAN-0105-adk-temporal-redesign.md).

Implementation scope: data-only payload proposals through a Python callable secret-disclosure recipe; ordinary ADK activities; Temporal round coordination, cancellation, worker restart, history replay and bounded child evaluation; immutable intent/evidence/result reconciliation; Docker-native pytest/coverage and pure scoped disposition rules; frozen development datasets, isolated producer/auditor evaluation and external whole-system scoring.

Qualification scope: genuine ADK scripted integration; actual Docker target execution; actual Temporal workflow/cancellation/restart/history tests; built-wheel resources; real-provider auditor fixtures. The live security producer request is provider-policy blocked and **is not qualified**. No population-level accuracy, hostile-interpreter observation integrity, multi-language support or production durability is claimed.

Latest handoff: [HANDOFF-0140](handoffs/HANDOFF-0140-code-quality.md). The dead-code/function/typing review passed 105 tests with actual Docker/Temporal and live-auditor gates enabled, plus a separate 6/6 frozen live-auditor evaluation. `make check` now enforces Ruff lint/format and warning-failing ty across maintained runtime/tests/evaluators. Read [code quality and review](../code-quality.md) for removals, function boundaries, logs, microbenchmarks and qualifications. Raw private outputs and credentials remain under ignored `.runs` and `.state`.
