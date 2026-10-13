---
id: HANDOFF-0075
kind: handoff
title: Agent package convention and scaffolding idea
status: recorded
updated: 2026-10-13
related: [IDEA-0006]
---

# Agent package convention and scaffolding idea

## Verified state

Documentation branch `docs/agent-package-convention` is based on `8606068f8e1792ca63636ff14c2f09c8c4317d1b` (main after PR #57). The original read-only review used `42a7273786a18ffaef0dbd005dfead12af83cbbf`; later main agent/evaluation improvements are not replaced or relabeled.

The user authorized recording the agent convention in `docs/development/ideas/` and submitting a PR, then asked to include a shared Claude/Codex scaffolding skill. Delivered scope is IDEA-0006 plus a CURRENT navigation entry and this handoff. The selected directory convention uses one file per model-facing tool under `tools/` with explicit native registration.

No source, tools, contracts, prompts, skills, runtime policy, pins, providers, generator, evaluator dataset, baseline or graph stage is changed. All proposed commands and the `corsair-agent-scaffold` skill are marked not implemented. This record does not expand live qualification. Resolve the eventual documentation commit with `git log -- docs/development/ideas/IDEA-0006-agent-package-convention-and-scaffolding.md`; do not infer a future SHA from this handoff.

## Validation and blockers

Passed: `git diff --check`; locked host-only `pytest -q tests/configuration/test_development_workflow.py --tb=short` with the repository `PYTHONPATH`: **5 passed in 2.60s**. This covers record IDs/states/references, local Markdown links, canonical Claude/Codex skill paths, CI permission/action guards and frozen held-out record guards. It does not prove agent behavior or client discovery. A local edit attempt to insert the CURRENT pointer did not match its context and made no replacement; the pointer was then appended without altering existing records, and the focused guards passed.

The full `make test-config` suite is not rerun for this documentation-only change; the focused guards are the proportionate selection. No live model, Temporal/OpenShell service, cluster/container, sandbox workload, authored test execution, or Claude/Codex client discovery is part of this scope. Skill/generator implementation and their client smoke tests remain unrun.

## Decisions and next steps

Keep the existing native PydanticAI/Temporal approach and same-factory direct/durable composition. Standardize package ownership, implementation identity and redacted receipts while retaining stage-specific tools, typed outcomes, trusted finalizers, budgets and authority.

Proposed shared skill source is `.claude/skills/corsair-agent-scaffold/SKILL.md`; Codex uses a Git symlink at `.agents/skills/corsair-agent-scaffold` to that canonical folder. The skill should guide deterministic generator dry-run, safe file creation, typed implementation, explicit per-tool/evaluator registration, isolated checks and normal review/handoff. It must not auto-wire the active graph, grant tools, overwrite unrelated work or claim qualification.

Next bounded implementation, if selected: write a focused spec/plan and standardize planning as the reference package, preserving public imports, model-facing bytes/schemas/IDs and replay contracts. Derive scaffold and conformance tooling from that proven layout, then add the thin shared skill. Do not refactor all agents, introduce a generic runtime framework or widen authority in the idea PR.

## Continuation prompt

```text
Read AGENTS.md, docs/development/CURRENT.md, IDEA-0006 and HANDOFF-0075. Inspect current main, working tree and open PRs; verify later agent changes and record-ID availability. Within the user's current scope, either review the documentation proposal or, if implementation is selected, write a focused spec/plan for planning's reference package and the deterministic scaffold/shared skill. Preserve native factories, tools/authority, prompt/skill bytes, contracts, direct/durable modes and replay identities. Run proportionate offline checks, agent evals and affected replay tests; client/live qualification remains separate. Update records/CURRENT and write a new handoff. Do not silently add agents, register unfinished tools or execute model-authored code on the host.
```
