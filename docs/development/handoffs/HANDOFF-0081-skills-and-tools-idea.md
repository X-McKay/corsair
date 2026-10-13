---
id: HANDOFF-0081
kind: handoff
title: Skills and tools working-interface proposal
status: recorded
updated: 2026-10-13
related: [IDEA-0007, IDEA-0006, SPEC-0023, SPEC-0044, SPEC-0052, PLAN-0056]
---

# Skills and tools working-interface proposal

## Verified state

Documentation branch: `docs/skills-tools-working-interfaces`, created from main `0ad9900c3bfd9a44fb3e5c4b3e4422313163dff8`. Resolve the published revision with Git after commit; no future SHA is asserted here.

The user requested a polished idea and a PR for review and consideration. Added [IDEA-0007](../ideas/IDEA-0007-skills-and-tools-working-interfaces.md) and a current-work pointer. The idea extends the earlier skills/tools review with current source references, clear responsibility ownership, optional native loading tradeoffs, tool usability improvements, evaluation criteria and a bounded authoring pilot.

The proposal preserves the now-implemented environment package convention and the accepted decision to use `toolset_sha256` in existing evaluation identity rather than introduce a manifest/receipt layer or generator. At the inspected base, PR #49, #44 and #63 are still open; overlapping witness, planning and setup work must be reconciled before implementation.

Only the idea, this handoff and `CURRENT.md` are changed. No application or developer skill, tool definition, evaluator, model/provider configuration, graph, contract, policy, dependency pin, baseline or runtime was modified. The idea remains `proposed`; publication is not design acceptance or qualification.

## Validation and blockers

Documentation/source references and native loading support were reviewed against the selected base and pinned PydanticAI 2.55.0. `git diff --check` passed. Using the existing locked Python 3.12 environment through `UV_PROJECT_ENVIRONMENT`, `uv run --locked python -m pytest tests/configuration/test_development_workflow.py -q` passed 5 focused record/link/skill/CI/held-out guards, and `make test-config` passed 1,230 offline checks in 179.98 seconds. One existing SDK `DeprecationWarning` reported no current event loop from `pydantic_graph/_utils.py`; no test failed.

Live model measurements, client discovery, deferred-capability provider/resume/replay behavior, sandbox replay of authored patches and runtime qualification were not run. They are not required to publish this documentation proposal and are not implied by its examples. No private run/state artifacts, raw provider/source exports or credentials are included.

## Decisions and next steps

Keep stable role/safety instructions always available and enforcement deterministic. Improve procedures and tool feedback before assuming a larger deferred-skill catalogue will help. Do not score skill loading as task success, infer private comprehension, or interpret missing observation as a clean trajectory.

Current authorization covers the idea and its PR only. If selected for implementation, write a focused spec/plan for authoring correction/finalization after reconciling PR #49 and current main. Define frozen baseline cases, treatment, comparison controls and regression dimensions. Structural package migration and semantic improvement should remain attributable separate changes. Optional resource loading is a later measured choice, not a prerequisite.

## Continuation prompt

```text
Read AGENTS.md, docs/development/CURRENT.md, IDEA-0007 and this handoff. Inspect current Git/source state and the latest decisions on PR #49, #44 and #63. Use the Corsair development and review skills. Review the skills-and-tools proposal against the accepted package convention and existing evaluation policy. Do not implement runtime changes merely because the idea PR exists. If the user selects the authoring pilot, write its narrow spec/plan, freeze controls and acceptance dimensions, and preserve witness authority and host non-execution. Run proportionate checks, record actual results and limits, update CURRENT.md and add a new handoff.
```
