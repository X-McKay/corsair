---
id: IDEA-0008
kind: idea
title: Optional per-agent release policies
status: deferred
updated: 2026-10-13
related: [IDEA-0009]
---

# Optional per-agent release policies

## Problem and evidence

A machine-readable acceptance policy could eventually make reviewed agent thresholds explicit and reproducible. The older InfoSec Harness kept `release-policy.yaml` alongside each agent dataset, with hard gates, numeric thresholds and required provenance. See its [partial-build policy](https://github.com/X-McKay/infosec-harness/blob/a1d6ec4ea1145f955a48519f578bb4824c519529/src/infosec_harness/agents/partial-build/evals/release-policy.yaml) and [gate evaluator](https://github.com/X-McKay/infosec-harness/blob/a1d6ec4ea1145f955a48519f578bb4824c519529/src/infosec_harness/evals/gates.py). The policy remains unchanged at the newer pre-replacement snapshot `5096f8ec41208d869bcfc353f90612bb59761681`; `7b192ac` replaces the staged system.

## Proposal and limits

If measured baselines later justify automated acceptance, add a small, strictly validated policy consumed by existing evaluation reporting. Keep it operator-owned and outside agent inputs. Reuse native Pydantic Evals results; do not introduce a release service, registry, experiment database or alternative evaluator framework.

Separate mandatory correctness/security checks from empirical quality and efficiency thresholds. Missing evidence must remain unknown, not pass. A host structural run cannot qualify sandbox execution. Bind any verdict to the policy digest, exact dataset/evaluator identity, candidate and model configuration, execution scope and observed coverage.

Do not copy the old defaults (75 percent success, $0.50 average cost, p95 of 12 requests). They are not measured Corsair requirements. The old parser can accept an empty policy, does not enforce its schema_version, and its inert-check audit is advisory. A future implementation would need strict schema validation, meaningful metric definitions, minimum sample/coverage requirements and explicit handling of inapplicable checks. Local-model token usage is useful even when dollar cost cannot be measured.

## Decision

Deferred following the user's direction to keep evaluation simple and prioritize understanding success, accuracy, tokens and latency. Improve the existing `make eval` summaries and baseline comparisons first, as proposed in [IDEA-0009](IDEA-0009-eval-runner-measurement.md). Revisit only when recurring review decisions show a need for stable automatic thresholds. This record authorizes no implementation or release gate.
