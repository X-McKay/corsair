---
id: PLAN-0105
kind: plan
title: Google ADK and Temporal durable-round redesign
status: implemented
updated: 2026-10-24
related: []
---

# Google ADK and Temporal durable-round redesign

User authorization: implement the recommended Plan 1 from scratch and push `manus/re-design` to X-McKay/corsair. Follow-up: align directories with the playbook reference architecture. This supersedes v2's framework, marker, negative-count and topology choices on this branch only; main and other branches are unchanged.

Base revision: d3da7d3f. The old implementation and data remain in Git history; the redesign deliberately starts a new source/test/evaluation tree rather than preserving incompatible executable paths.

## Scope and decisions

Google ADK handles bounded producer/auditor invocations in ordinary Temporal activities. Temporal owns rounds, root budgets, failure handling, durable results and bounded child fan-out. No native Alpha integration or custom agent checkpoint loop. No unsupported negative clearance.

Initial supported workload: Python callable secret-disclosure verification. Agents propose declarative payloads and plan revisions, not executable assertions. An operator-owned native pytest/coverage driver invokes the unchanged target in isolated Docker containers, while a random private fixture prevents a producer from supplying canned secret content. Target source remains untrusted: isolation and adversarial tests are separate from observation correctness, and this is not a universal proof mechanism.

Directory mapping follows `agent-playbook/02-reference-architecture.md`: private factories/instructions/tools under `agents/<role>`, nondeterministic work under `steps`, deterministic coordination under `workflows`, platform artifacts/models/worker under `runtime`, shared security tools under `tools/security`, verdict policy under `policy`, datasets/evaluators/experiments/fixtures/baselines under `evals`, and risk/runbook/deployment material in their named directories. Shared wire contracts have one definition in `contracts.py`, not copied agent schemas. Agent metadata will reference those canonical schemas. No empty capability catalogs.

## Build and validation

1. Canonical contracts, immutable artifact operations and pinned SDK installation.
2. Trusted Python recipe, source snapshots, Docker hardening and verifier conformance.
3. ADK producer/auditor factories, package resources, frozen isolated evaluation cases.
4. Durable round workflow, activity composition, CLI and eval scorer.
5. Real provider, real Temporal and real Docker tests where available; preserve concrete blockers.
6. Review, clean up, run the full suite again, test the built wheel outside the checkout, and push only this branch.

## Observed setup

- GitHub connector enabled; repository write permission and branch creation succeeded.
- Pinned dependencies installed: google-adk 2.13.0, temporalio 1.34.0, docker 7.2.0.
- Provisioned and qualified actual rootless Docker and a native Temporal local server.
- Genuine ADK scripted investigations, Docker-native control/adversarial/fixed observations, actual CLI frozen-batch scoring, Temporal cancellation/restart/history replay, and fresh installed-wheel resources were executed.
- Real-provider auditor development fixtures exposed a hypothesis-coherence failure; packaged prompt improvement passed all six repeated attempts across the two frozen dev cases. This is not a held-out accuracy claim.
- The live security producer was blocked by provider cyber policy. Its request was not evaded or switched to another provider, and it remains unqualified. Native scripted integration is separately labelled.
- Five independent review findings were remediated with explicit regressions; see [review remediation](../review-remediation.md) and the final handoff for exact commands and receipts.
