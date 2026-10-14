---
id: IDEA-0010
kind: idea
title: Native agent manifests and operator policy
status: accepted
updated: 2026-10-13
related: [SPEC-0079, PLAN-0094, SPEC-0080, PLAN-0095, IDEA-0006, IDEA-0007]
---

# Native agent manifests and operator policy

## Problem and evidence

The user proposed per-package `agent.yaml`, a standard agent base class and separate model/budget policies while the independent-probe baselines were running. The user subsequently authorized behavior-preserving implementation before the current baseline PR; the earlier after-PR sequencing is superseded; no manifest migration or policy resolver is implemented by this record.

Corsair pins `pydantic-ai-slim==2.55.0`. Local inspection confirms native `AgentSpec`, `Agent.from_spec()` and `Agent.from_file()` with explicit native model, dependencies, output validator, validation context and capabilities supplied in Python. Prefer that facility and a small shared construction helper where repetition is demonstrated. A custom inheritance framework, scheduler or provider protocol is unnecessary. The pinned spec schema is authoritative: the external example includes harness-specific metadata and settings that cannot be assumed supported or enforced by Corsair.

## Proposal and limits

Suggested responsibilities:

- Package manifest: purpose, description, static instructions, selected capabilities/skills and version metadata. Keep procedure in the referenced skills; avoid duplicating it in YAML and Python.
- Operator policy: named provider/model profiles, request settings, per-agent run ceilings and retries. Extend existing typed inference configuration and `CompositionBudget` semantics; do not create competing defaults. Keep policies outside investigated-source authority and preserve explicit provider selection. No credentials belong in manifests.
- Python: domain input/output contracts, current-run source/artifact validation, restricted tools, input-derived limits and native Temporal bindings. Preserve all role boundaries and immutable pre-execution review.

Model settings limit a response; native `UsageLimits` and the existing tool-budget capability enforce run allowances. Arbitrary YAML metadata is descriptive until typed code explicitly validates and enforces it. Receipts must bind manifest, policy, skill, tool and factory identities and record effective limits, not only named profiles. Direct, durable and isolated evaluation must resolve the same admitted configuration, with explicit fixture overrides.

## Decision

Accepted for implementation in the current PR under the later user instruction, superseding the earlier after-publication dependency. [SPEC-0080](../specs/SPEC-0080-native-agent-manifests.md) records the accepted boundaries; [PLAN-0095](../plans/PLAN-0095-native-agent-manifests.md) is in progress. Preserve prior frozen results and identify migrated-source parity/baselines separately. Acceptance for a future refactor: preserve complete rendered instructions, capability/tool definitions, contracts and validators, output retries, input-derived budgets, provider settings and native durability behavior. Compare each affected agent against the frozen baseline; count missing telemetry as unknown. Reject unrecognized capabilities/settings and untrusted repository manifests. Keep exactly two native issue probes, independent control/exploit authors and outcome-blind immutable validity. Do not adopt the reference harness's marker-based verdict protocol.

Sources reviewed: [user-linked manifest](https://github.com/X-McKay/infosec-harness/blob/feature/claude-refactor/src/infosec_harness/agents/probe-author/agent.yaml), read through the GitHub contents API; [native agent-spec documentation](https://pydantic.dev/docs/ai/core-concepts/agent-spec/), checked against the installed pinned SDK. Implementation is in progress; this decision is not a completed migration or new runtime qualification.
