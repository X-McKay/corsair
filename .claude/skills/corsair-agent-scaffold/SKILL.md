---
name: corsair-agent-scaffold
description: Use when creating a new Corsair agent, adding a model-facing tool to an agent, or moving an existing agent package to the standard layout. Follows docs/agent-packages.md, trusted native AgentSpec manifests and operator policy; there is no generator.
---

# Corsair agent scaffold

Read [the agent package convention](../../../docs/agent-packages.md) first; it is authoritative and this skill does not repeat it. Use `corsair-development` for records and `corsair-review` before finishing. This skill grants no tools, approves no graph integration and certifies nothing.

For investigation agents and tools, preserve the shared unit-test-first contract across languages/frameworks/CWEs: exactly two native tests through existing real application seams; controlled dependencies retain the real logic owning the security property; source/condition/assertion validity is distinct from execution admission. Optional witnesses provide bounded supporting evidence. Do not add mandatory language-specific recorders or let missing database/filesystem telemetry alone reject a valid unit test. Evaluate both a sound seam-based test and invalid substitute/irrelevant assertions.

## New agent

1. Confirm the objective is a new role rather than a change to an existing agent. Write its spec: typed input and outcomes, narrow ports, authority, failure layers and the frozen eval set it ships with.
2. Create only files whose responsibilities exist. Check current migrated packages and `corsair.agents.spec` before copying a reference; all seven current factory variants use trusted native manifests, including repository identification.
3. Add trusted package `agent.yaml` with only native name/description/literal instructions and the descriptive config/prompt-version metadata. Keep static boundary instructions there once and procedure in owned skill files; `prompts.py` renders typed input and exposes compatible identities. Load its fixed trusted package path with native `AgentSpec.from_file(...)`. Never discover/load investigated-repository manifests or arbitrary capability imports.
4. Build directly through native `AgentSpec.from_file(...)` and `Agent.from_spec(...)`, passing the explicit operator-selected native model, Python dependencies/output validator, explicit Python capability instances, retries/validation context and optional native Temporal durability. Keep schemas, validators, restricted tools, authority and durability in Python. Keep capability authority/order explicit in Python; YAML has no selector. `factory_identity` hashes provenance only and does not construct agents. Keep owned skill files and current eager procedure loading. SDK-agnostic schemas/adapters are deferred. Do not introduce a custom base-class hierarchy or marker protocol.
5. Put each model-facing tool in `tools/<tool_name>.py` and register it in `tools/toolset.py`; export `TOOLSET_SHA256` and pin it in a toolset test that also checks exact names, order, id and retries.
6. Unimplemented behaviour must fail clearly. Never return a fabricated `ready` or register an unfinished tool. The agent starts unwired from any chain or workflow.
7. Add the eval set under `evals/<role>/`, write `toolset_sha256` to its `configuration.json`, add a `SUITES` entry in `evals/run.py`, and run `make eval AGENT=<role>` scripted. Model-written code is never executed on the host; native host fixtures admit only exact operator-reviewed bytes.

## Operator policy and identity

Reuse explicit `InferenceConfig` loading and the typed `CompositionBudget`/input-derived limits. JSON provider compatibility remains; operator YAML uses the same validation, never a second credential/provider resolver or competing defaults. Packaged model policy is an inert example unless explicitly selected. Use the validated packaged budget default or an explicit operator-owned override; investigated agents cannot modify policy or select arbitrary files.

Record resolved manifest, policy, skill/tool/factory hashes and effective settings, limits and retries in native receipts. Compare direct, durable and isolated resolution; preserve old histories and measurements. Missing telemetry is unknown. Changing a manifest, skill, policy or helper requires relevant parity checks and isolated role baselines before composing it; loading YAML or passing structural checks alone is not semantic or runtime qualification.

## New tool on an existing agent

1. Add `tools/<tool_name>.py` with the callable, annotated arguments, docstring description and returned observation model.
2. Register it in `tools/toolset.py` in the intended offered position. Update the toolset test's names and pinned digest in the same change, and say why the model should be offered it.
3. Run the agent's tests and `make eval AGENT=<role>`; report the `toolset_sha256` change and any score change against the baseline.

## Moving an existing agent

Follow "Moving an agent to the convention" in the convention document. The move must not change what the model is offered: capture before and after, require byte equality, and compare `make eval` runs. Inspect concurrent package changes and coordinate owners; preserve unrelated work and the user's current authorization. For native-spec migration compare rendered instructions, capability/tool schemas/order, contracts/validators, request settings, retries, derived limits and native durability before migrating the next role.

## Native optional skill loading

When enabling directory discovery or progressive disclosure, use PydanticAI Harness `Skills` rather than implementing another loader. First verify and pin its dependency against the admitted core SDK, then test native activation and validator/budget/durability interactions. Current eager factories do not already provide this behavior. `Skills` loads skill instructions; it does not itself read referenced resources or run scripts. Keep trusted package skill content separate from investigated source and preserve explicit tool authority.
