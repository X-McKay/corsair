---
id: SPEC-0080
kind: spec
title: Native agent manifests and operator policy
status: accepted
updated: 2026-10-13
related: [IDEA-0010, PLAN-0095, SPEC-0079, PLAN-0094]
---

# Native agent manifests and operator policy

## Goal and scope

Implement the user-authorized, behavior-preserving native manifest/operator-policy migration in the current PR. The later user instruction supersedes the earlier after-baseline-PR dependency. Preserve completed and interrupted baseline receipts and source archives; migrated source receives new identities and separate per-role measurements rather than retroactive parity or score claims. Use pinned PydanticAI 2.55.0 native `AgentSpec`, `Agent.from_spec()`/`Agent.from_file()` and a small shared construction helper for demonstrated repetition. Do not introduce a custom base-class hierarchy, scheduler, provider protocol or generic orchestration layer.

Preserve six roles, independent control/exploit contexts and own-file authority, exactly two native probes, ordinary benign controls, faithful adversarial safety tests and a separate immutable outcome-blind validity review before execution. Retain typed dispositions and deterministic gates; no marker-based verdict protocol is admitted.

## Boundaries and design

Trusted package-owned `agent.yaml` expresses supported native purpose/instruction/capability selection. Procedure remains in referenced skills. The locally verified pinned `AgentSpec` schema is authoritative: purpose/version metadata or instrumentation options from the linked harness are not assumed native fields, active behavior or enforcement. Verify supported fields and reject unknown ones before implementation. If descriptive metadata is needed outside the native schema, demonstrate that need and validate a narrow package wrapper rather than implicitly accepting arbitrary YAML.

Python retains typed inputs/outputs, dependencies, output validators and current-run source/artifact admission; restricted tool registration and authority; native durability bindings; and explicit runtime integration. A tiny shared factory assembles those supplied objects through native SDK construction. It does not discover arbitrary imports/capabilities, infer tools from manifest strings, or let manifests expand authority.

Operator policy reuses existing `InferenceConfig` validation and `CompositionBudget`/input-derived limit semantics. Profiles, request settings, ceilings and retries have one authoritative resolution path, shared by direct, durable and isolated evaluation. Preserve explicit operator-owned JSON provider compatibility. An operator-owned YAML schema may extend the existing typed configuration if needed; it must not duplicate credential/provider logic, establish competing defaults or silently fall back. Secrets remain outside manifests. Response settings, run usage limits and tool-budget enforcement remain distinct native controls.

Investigated repositories cannot provide active agent manifests or edit operator policy. Load only trusted package resources and explicit operator configuration; reject repository `agent.yaml`, unknown capabilities/settings and arbitrary capability imports. Receipts record resolved manifest/policy/skill/tool/factory hashes, complete effective settings, output retries and derived limits. Missing telemetry remains unknown.

## Acceptance and validation

Pilot control and exploit packages first, then migrate environment, inline/repository identification, planning and assessment one bounded role at a time after each parity check. Freeze legacy construction outputs and compare native construction for complete rendered instructions, capability/tool names and schemas, input/output schemas, dependencies, validators, request settings, role retries, budget enforcement and effective input-derived limits. Preserve literal narrow role prompts and author ownership. Native SDK loading alone is not parity.

Use the same frozen isolated cases and provider/settings, then compare contract, trajectory, grounding, robustness/security, consistency and efficiency against the published baseline. Separate actual generated-body review from assertion metadata and native execution. Demonstrate direct/durable factory and configuration parity, retain old saved histories/replay evidence, and check new histories without rewriting old ones. Fixture/replay success does not admit live provider, runtime or production durability qualification.

Migrate one later role at a time only after the pilot's parity and isolated baseline checks pass. Keep the prior package available for attributable comparison until its replacement is admitted. Stop dependent migration on unsupported native schema fields, changed authority/instructions/settings, incompatible histories or unresolved baseline regression; independent planning may continue.

## Decisions and open questions

The user now authorizes implementation before publishing the current PR; [PLAN-0095](../plans/PLAN-0095-native-agent-manifests.md) is in progress. This supersedes the earlier publication dependency. Helper, policy and role migration are being implemented by their separate owners; final parity, migrated-source measurements and qualification remain pending. Resolve the smallest policy YAML surface and any descriptive metadata need from the pinned schema and existing configuration before coding. This acceptance does not merge/deploy the baseline PR or close semantic validity issues.
