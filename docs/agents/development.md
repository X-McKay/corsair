# Developing agent roles

Change an agent as one bounded component: keep its objective, typed contract, tools, prompt, procedural guidance, native factory, and isolated evaluation aligned. The two roles are not a platform for adding general agents, provider wrappers, tool catalogs, or automated repair behavior. Architectural ownership is in the [architecture overview](../architecture/overview.md); active work is indexed in the [plans](../plans/README.md).

## Authoritative implementation locations

| Concern | Canonical location | Change boundary |
| --- | --- | --- |
| Producer behavior | [`src/corsair/agents/producer/`](../../src/corsair/agents/producer/) | Prompt, source-read tools, role toolset, source-grounding procedure, and `ProducerDecision` factory configuration. |
| Auditor behavior | [`src/corsair/agents/auditor/`](../../src/corsair/agents/auditor/) | Prompt, role toolset, semantic-review procedure, and `AuditResult` factory configuration. |
| Role metadata and packaged resources | [`src/corsair/agents/resources.py`](../../src/corsair/agents/resources.py) and each role's `agent.json`, `instructions/system.md`, and `skills/` | Metadata validates the factory's approved surface; resources load from the installed package, not the checkout. |
| Wire contracts | [`src/corsair/contracts/agents.py`](../../src/corsair/contracts/agents.py) | Define or change a Pydantic model once; role-local `contracts.py` modules are object-identity re-exports for role-local imports, not schemas. |
| Native episodes | [`src/corsair/adapters/inference/adk.py`](../../src/corsair/adapters/inference/adk.py) | Fresh ADK runner, callbacks, accounting, packet construction, output validation, and bounded skill-load accounting. |
| Isolated evaluation and scoring | [`src/corsair/evaluation/`](../../src/corsair/evaluation/) | Frozen fixture loading, agent invocation, and external scoring. |

`agent.json` is Corsair's validated JSON role metadata. The `SKILL.md` YAML frontmatter names and describes a packaged procedure for native ADK loading. Neither replaces the other, and neither is an ADK YAML Agent Config or a new Corsair configuration DSL. Factories remain ordinary native Python construction with the installed ADK APIs.

## Preserve these role invariants

- The producer has exactly its episode-local source readers, pure `preview_invocation`/`relative_path` helpers and private native skill-loading surface. The helpers perform bounded in-memory mechanics, never target or filesystem execution. The auditor has only its private native skill-loading surface, remains fresh-context and outcome-blind, and never receives a source, mechanical, execution, network, or external tool.
- Skill catalogs are explicitly role-filtered, initialized by native `SkillToolset` in `EAGER` mode, and load only built-package `SKILL.md` bodies or admitted resources through `load_skill` and `load_skill_resource`. A skill is guidance loaded into context, not executable code, a state injector, or an additional tool registry.
- Factories use native `LlmAgent.output_schema` with canonical `ProducerDecision` or `AuditResult`. A producer decision is either a `proposal` containing the unchanged `Submission` or `no_grounded_candidate` with a bounded reason. Do not reintroduce a custom `submit` function, termination state, string decoder, or schema-repair layer.
- Model capability determines whether ADK can combine schema output and ordinary tools directly or uses its own schema-completion fallback. Keep native callbacks, call/output/tool budgets, and post-generation Pydantic plus round/parent validation in force for both paths. Count skill loading within the established finite ceilings.
- Provider credentials stay in the worker environment. A model setting selects the native Gemini or LiteLLM route; it is not a credential broker or an invitation to add provider-specific placeholders.
- The model episode is an ordinary bounded Temporal activity. Do not substitute an upstream Google ADK Temporal integration, invent an agent graph, or add an implicit retry/fallback loop.
- A `no_grounded_candidate` decision is an explicit terminal abstention for a newly recorded workflow history: it records the producer usage and prepared provenance, executes no target or audit, and remains `INCONCLUSIVE`. The Temporal patch marker preserves the preceding command path for old histories. It never establishes negative clearance.

The producer's snapshot reader, the Docker sandbox, evidence verifier, artifact store, and final policy belong to trusted components. They must not be moved into an agent prompt, skill, or tool surface to make an evaluation pass.

## Focused change loop

1. Read the relevant factory, prompt, metadata, role contract re-export, toolset, procedural skill, native runner, and frozen evaluation before changing role behavior. Keep the public packet outcome-blind and keep labels/oracles external.
2. Make the smallest role-local change. Add a procedural skill only for reusable guidance; do not add scripts, assets, code execution, mutable state, remote loading, or a placeholder policy/registry. If a contract changes, update actual consumers rather than creating a duplicate documentation or compatibility schema.
3. For any skill content or capability change, qualify the new resource digest and capability identity and ensure the resource loads from an installed wheel outside the checkout. Record successful loader names through the sanitized bounded accounting path; record unavailable usage or cost as unknown.
4. Run proportionate offline checks from the repository root:

   ```bash
   just check
   just -- test tests/unit/test_agents.py tests/unit/test_agent_evaluator.py
   ```

5. Run the affected frozen isolated evaluation with an explicitly configured worker/provider environment. The supported entry point is `just eval-agent`, described in [agent evaluations](evaluations.md). A deterministic native-ADK test double is useful for regression coverage but is not a live-model result.
6. If a change reaches composition, retain the separate Docker/Temporal/native-evidence and external-scoring result. Do not treat an isolated fixture result as evidence of target execution, security efficacy, or durable workflow behavior.

Nix and `uv.lock` pin the development tools and Python dependencies, but they do not make the full application/container path hermetic; Docker, the selected model service, and host state remain external. Supported developer targets are macOS arm64 and Linux amd64 only; consult the [platform reference](../reference/platforms.md) before making a platform claim.

## Core preload versus optional progressive loading

The required role procedure is parsed from its private packaged SKILL.md by native ADK during controlled factory assembly and its instruction body is present in LlmAgent.instruction before the first model request. This avoids relying on a structured-output model to choose a loading tool. Usage.skills_preloaded and agent.skill_preloaded describe actual preparation, not model compliance or tool execution. Optional native load_skill refreshes and load_skill_resource reference requests remain available within finite root/episode budgets; only successful model-requested loads populate Usage.skills_loaded, and their dispatches count as tool calls. The configured provider skipped optional loading in the earlier diagnostic stage; those reports remain retained rather than rewritten as successful tool use.
