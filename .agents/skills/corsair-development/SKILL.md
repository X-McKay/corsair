---
name: corsair-development
description: Apply Corsair's bounded, SDK-first development workflow when planning, implementing, reviewing, or testing repository changes. Use for source, schema, agent, adapter, workflow, documentation, or package-resource work that requires explicit ownership, privacy, and qualification discipline.
---

# Corsair development workflow

Use this maintainer workflow for a bounded change. Treat it as development guidance only; it does not add a runtime skill, tool, provider, or agent capability.

## Establish the boundary

1. Read [repository instructions](../../../AGENTS.md), [development conventions](../../../docs/development/conventions.md), [testing](../../../docs/development/testing.md), and [extension qualification](../../../docs/guides/extensions.md) before editing. For agent work, also read [agent development](../../../docs/agents/development.md) and [tools and runtime instructions](../../../docs/agents/tools-and-skills.md).
2. Identify one owning layer and its consumers. Keep role-local factories, prompts, metadata, and private tools under `agents/`; define canonical Pydantic contracts once in `contracts/`; keep domain ports in `ports/`; and use real SDK implementations in `adapters/`. Do not introduce a second agent loop, scheduler, retry broker, graph, provider registry, or placeholder backend.
3. Start from installed, pinned SDK behavior. Declare the canonical output schema on the native factory rather than adding a string repair path, compatibility state, or duplicate wire model.
4. Preserve unrelated work and local state. Do not clear, apply, overwrite, inspect for content, or commit another contributor's changes or stashes. Keep `.state/`, `.runs/`, credentials, private diagnostics, and disposable `.work/` material private; do not turn them into source, package data, logs, or evidence claims.

## Implement one concrete change

1. Read the canonical schema, settings, factory, consumer, and relevant frozen input before changing behavior. Keep workflows deterministic; place filesystem, model, network, and Docker I/O in ordinary activities or adapters.
2. Make the smallest complete change in its owning location. Name every function for one intuitive responsibility. Prefer direct composition over speculative layers, broad type ignores, or generic extension points.
3. Preserve the evidence boundary. Models propose data only; trusted components produce observations; evaluators retain labels and oracles outside agent, tool, and workflow packets. Do not weaken sandboxing, source admission, cleanup, or provider settings to make a result pass.
4. Update current documentation or records only when the implemented behavior changes. Link authoritative source and guides instead of copying mutable settings, schemas, or historical commands. Keep active work and qualification limits in the [plans index](../../../docs/plans/README.md).

## Test, clean up, retest, and package

1. Run the smallest meaningful test and its affected consumers first. Run the maintained quality gate from the repository root:

   ```bash
   just check
   just -- test -q -W error
   ```

2. Run Docker, Temporal, or provider checks only with their explicit reviewed prerequisites. Report unrun, skipped, failed, and operational boundaries as such; a mock, provider error, or skipped native test is not equivalent to a qualified result.
3. Remove only dead code and disposable artifacts owned by the change. Recheck dynamic SDK callbacks, Pydantic validators, and Temporal registrations before treating a static report as dead code.
4. Repeat the affected tests after cleanup. Then build and inspect the exact public package:

   ```bash
   just build
   ```

   Ensure the built package loads its resources outside the checkout and contains only authorized public source, tests, documentation, and package resources. Exclude caches, private state, credentials, raw reasoning, evidence blobs, and delivery archives.
5. Record the exact commands, outcomes, warning/skip counts, applicable configuration identity, and remaining blockers in the current plan or handoff. Do not claim broad security, durability, model-quality, cost, or publication results beyond the executed boundary.
