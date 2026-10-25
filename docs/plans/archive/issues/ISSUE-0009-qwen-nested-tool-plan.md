---
id: ISSUE-0009
kind: issue
title: Supplied Qwen endpoint returns nested tool plan as a string
status: resolved
updated: 2026-10-25
related: [PLAN-0109, HANDOFF-0141]
---

> Historical record. Commands, counts and status describe the recorded revision, not the current working tree. See [current work](../../README.md) for current guidance.

# Supplied Qwen endpoint returns nested tool plan as a string

Physical-Mac qualification uses the user-selected HTTPS OpenAI-compatible endpoint and its advertised `Qwen3.6-35B-A3B-NVFP4`, through native ADK LiteLlm with explicit `reasoning_effort=none`. The unchanged auditor frozen cases passed 6/6. Producer frozen case01 failed 3/3: nine genuine model calls and nine tool calls; every final proposal passed `plan` as a JSON-encoded string instead of an object. Canonical `Submission`/`PlanRevision` validation correctly rejected every attempt with `producer_invalid`. No target was executed during isolated evaluation; no full live chain is admitted from these results.

Native SDK declaration inspection shows `parameters_json_schema.properties.plan` is `{"$ref":"#/$defs/PlanRevision"}` and the referenced definition is a closed object with its required fields and bounds. Raw declaration is retained privately at `.work/mac-e2e-20261025/submit-declaration.json`; attempted model receipts/reports are under `.runs/mac-e2e-20261025/producer-eval.json`. The endpoint does not expose its root version/OpenAPI metadata. These observations establish a tool-argument interoperability failure, not proof that a specific serving parser or model is solely responsible.

A small exploratory Pydantic annotation (`json_schema_extra` with object type) was inspected without making further model calls; native ADK did not emit the extra type. The annotation was reverted. No ad-hoc JSON-string decoder, schema repair framework, contract relaxation, provider fallback, prompt change or larger frozen budget is installed to obtain a pass.

Resolution requires a native SDK/serving configuration that delivers the canonical object, retained baseline comparison against the unchanged producer freeze, and producer success before composing the live model with the durable native chain. Independently qualified scripted-ADK/Docker/Temporal behavior and live-auditor behavior remain distinct.

## Resolution: native structured output (2026-10-25)

The producer now declares `Submission` directly as ADK `LlmAgent.output_schema`, with nested Pydantic `PlanRevision`; custom submit tooling and terminal state are removed. ADK's native configured model capability selects direct schema-plus-tools output. The domain JSON union is explicit so native generation receives actual payload type choices rather than JsonValue's unconstrained `{}`. Pydantic validation and dynamic round/parent checks remain strict, and all supported JSON value types remain accepted. Native callbacks retain call budgets and usage, including ADK's own schema-tool fallback on other models.

The initial native-schema attempts solved plan validation but still failed exact payload matching; these failures are retained. Generic source-grounded payload/argument guidance and hypothesis/plan-before-payload schema ordering then passed the unchanged producer freeze **3/3**, with 3 LLM calls, 0 tool calls, 2910 input/845 output tokens, compared with the original 0/3, 9 LLM/9 tool calls, 11689 input/1713 output tokens. Auditor remained 6/6. No oracle/dataset hashes, exception policies, SDK pins or budgets changed. This is three repeats of one diagnostic producer case, not a population accuracy result.

Actual live durable composition was subsequently admitted and scored 2/3; its safe-case follow-up error is a separate tracked semantic limit under [ISSUE-0010](../../active/ISSUE-0010-live-safe-case-probe.md). The original nested-object validation blocker is resolved, not silently decoded or bypassed.
