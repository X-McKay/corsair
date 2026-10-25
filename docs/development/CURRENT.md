# Current work

The `manus/re-design` branch is a from-scratch Google ADK + Temporal rebuild, authorized on 2026-10-24. It implements the recommended durable-round Plan 1. The layout follows the user's linked agent-playbook reference architecture. The previous v2 source, corpus, OpenShell stack and records remain accessible in Git history at base `d3da7d3f`; they are not executable compatibility paths in this branch.

Canonical behavior is described in [README](../../README.md), [architecture and ownership](../architecture.md), [risk assessment](../../src/corsair/runtime/risk.md), and [PLAN-0105](plans/PLAN-0105-adk-temporal-redesign.md).

Implementation scope: data-only payload proposals through a Python callable secret-disclosure recipe; ordinary ADK activities; Temporal round coordination, cancellation, worker restart, history replay and bounded child evaluation; immutable intent/evidence/result reconciliation; Docker-native pytest/coverage and pure scoped disposition rules; frozen development datasets, isolated producer/auditor evaluation and external whole-system scoring.

Qualification scope: genuine ADK scripted integration; actual Docker target execution; actual Temporal workflow/cancellation/restart/history tests; built-wheel resources; real-provider auditor fixtures. The live security producer request is provider-policy blocked and **is not qualified**. No population-level accuracy, hostile-interpreter observation integrity, multi-language support or production durability is claimed.

Latest handoff: [HANDOFF-0138](handoffs/HANDOFF-0138-adk-temporal-redesign.md). Review actual receipts and run the copyable next actions there before extending capabilities. Raw private reports and credentials stay under ignored `.runs` and `.state`.
