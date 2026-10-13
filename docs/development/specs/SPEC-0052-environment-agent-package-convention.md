---
id: SPEC-0052
kind: spec
title: Agent package convention, environment reference and toolset identity
status: accepted
updated: 2026-10-13
related: [IDEA-0006, SPEC-0044, SPEC-0029, PLAN-0056]
---

# Agent package convention, environment reference and toolset identity

## Goal and scope

Give every agent package the same responsibility layout, with one module per model-facing tool and explicit registration, so agents can be read, reviewed and evaluated the same way. This spec adopts IDEA-0006 with the owner's selected changes (2026-10-13): identity is one field added to the existing SPEC-0044 run identity instead of a new manifest/receipt layer; the shared skill is a thin guide to the convention with no generator; the environment agent is the reference package because no open PR changes it.

In scope: the [convention document](../../agent-packages.md); the environment package split; `toolset_sha256` in the environment eval identity and `make eval` comparison; the `corsair-agent-scaffold` skill. Out of scope: other agents (each follows under its own plan once its open PRs merge), IDEA-0006 section D receipts, section F generator and conformance commands, any prompt, tool, budget, contract or chain change.

## Boundaries and design

- Environment layout after the split: `agent.py` (factory), `prompts.py` (instructions, prompt version, skill text and digest, prompt rendering), `dependencies.py` (execution port, handle, operator budget, ledger), `validation.py` (trusted finalizer), `tools/{read_source,list_toolchains,run_setup_command,read_output}.py`, `tools/toolset.py`. `contracts.py` and `frameworks.py` are unchanged; the runtime hand-off's `EnvironmentInput` contract is untouched.
- Registration uses native `FunctionToolset.add_function` with explicit names and retries in the original offered order and the original toolset id. No scanning or dynamic import.
- `TOOLSET_SHA256` is the SHA-256 of the toolset id and every field of each native `ToolDefinition` plus its retry limit, in order. It is computed from the native objects, not a hand-written list.
- Old import paths stay valid: `agent.py` re-exports the prompt and skill names; `tools` re-exports `EnvironmentDependencies`, `SetupBudget` and `SetupLedger`.
- `evals/run.py` adds `toolset_sha256` to the identity keys it copies and compares. Suites that do not report it leave it absent; older runs show it as `null`, which is unknown, not a change in tools.

## Acceptance and validation

- What the model is offered is byte-identical before and after: instructions, rendered prompt, every tool definition, output tools, text-output flag, toolset id and per-tool retries, captured through a recording `FunctionModel`.
- The digest computed on the pre-split source equals the post-split digest; a toolset test pins it with names, order, id and retries.
- Existing environment tests and the runtime hand-off test pass unchanged apart from the dependency import path.
- `make eval AGENT=environment` scripted gives the same assertions, cases and clean attempts before and after; the only identity difference is `toolset_sha256` appearing.
- `make test-config` passes, including the skill link and record guards.

This is an implementation check; it qualifies no live provider, sandbox or durable behaviour.

## Decisions and open questions

- Owner direction (Al, 2026-10-13): adopt the recommended variant, and cascade across all agents if successful. The cascade is planned in [PLAN-0056](../plans/PLAN-0056-agent-package-convention.md) and waits for #49 and #44, which change planning, authoring, assessment and identification.
- `toolset_sha256` lives in the environment package until a second agent adopts it; the first follow-on move promotes the helper to a shared module (second consumer).
- Receipts (section D) and the generator (section F) remain proposed in IDEA-0006 until a concrete consumer or a new agent needs them.
