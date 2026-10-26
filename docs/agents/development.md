# Developing agent roles

Change an agent as one bounded component: keep its objective, typed contract, tools, prompt, procedural guidance, native factory, and isolated evaluation aligned. The two roles are not a platform for adding general agents, provider wrappers, tool catalogs, or automated repair behavior. Architectural ownership is in the [architecture overview](../architecture/overview.md); active work is indexed in the [plans](../plans/README.md).

## Authoritative implementation locations

| Concern | Canonical location | Change boundary |
| --- | --- | --- |
| Producer behavior | [`src/corsair/agents/producer/`](../../src/corsair/agents/producer/) | Prompt, source-read tools, role toolset, source-grounding procedure, and `ProducerDecision` factory configuration. |
| Auditor behavior | [`src/corsair/agents/auditor/`](../../src/corsair/agents/auditor/) | Prompt, preloaded semantic-review procedure, and tool-free `AuditResult` factory configuration. |
| Role metadata and packaged resources | [`src/corsair/agents/resources.py`](../../src/corsair/agents/resources.py) and each role's `agent.json`, `instructions/system.md`, and `skills/` | Metadata validates the factory's approved surface; resources load from the installed package, not the checkout. |
| Wire contracts | [`src/corsair/contracts/agents.py`](../../src/corsair/contracts/agents.py) | Define or change a Pydantic model once; role-local `contracts.py` modules are object-identity re-exports for role-local imports, not schemas. |
| Native episodes | [`src/corsair/adapters/inference/adk.py`](../../src/corsair/adapters/inference/adk.py) | Fresh ADK runner, callbacks, accounting, packet construction, output validation, and bounded skill-load accounting. |
| Isolated evaluation and scoring | [`src/corsair/evaluation/`](../../src/corsair/evaluation/) | Frozen fixture loading, agent invocation, and external scoring. |

`agent.json` is Corsair's validated JSON role metadata. The `SKILL.md` YAML frontmatter names and describes a packaged procedure for native ADK loading. Neither replaces the other, and neither is an ADK YAML Agent Config or a new Corsair configuration DSL. Factories remain ordinary native Python construction with the installed ADK APIs.

## Preserve these role invariants

- The producer has exactly its episode-local source readers and a preloaded procedure, with no skill loader. The auditor has no tools (its procedure is preloaded), remains fresh-context and outcome-blind, and never receives a source, execution, network, external, or skill-loading tool.
- Neither role composes a native `SkillToolset`; `AgentSpec` rejects any loader tool. Each factory parses only built-package `SKILL.md` bodies through the admitted native loader path and preloads them into the instruction. A skill is guidance in context, not executable code, a state injector, or an additional tool registry.
- Factories use native `LlmAgent.output_schema` with canonical `ProducerDecision` or `AuditResult`. A producer decision is either a `proposal` containing the unchanged `Submission` or `no_grounded_candidate` with a bounded reason. Do not reintroduce a custom `submit` function, termination state, string decoder, or schema-repair layer.
- Model capability determines whether ADK can combine schema output and ordinary tools directly or uses its own schema-completion fallback. Keep native callbacks, call/output/tool budgets, and post-generation Pydantic plus round/parent validation in force for both paths. Neither role has a skill loader to count.
- Provider credentials stay in the worker environment. A model setting selects the native Gemini or LiteLLM route; it is not a credential broker or an invitation to add provider-specific placeholders.
- The model episode is an ordinary bounded Temporal activity. Do not substitute an upstream Google ADK Temporal integration, invent an agent graph, or add an implicit retry/fallback loop.
- A `no_grounded_candidate` decision is an explicit terminal abstention for a newly recorded workflow history: it records the producer usage and prepared provenance, executes no target or audit, and remains `INCONCLUSIVE`. The Temporal patch marker preserves the preceding command path for old histories. It never establishes negative clearance.

The producer's snapshot reader, the Docker sandbox, evidence verifier, artifact store, and final policy belong to trusted components. They must not be moved into an agent prompt, skill, or tool surface to make an evaluation pass.

## Focused change loop

1. Read the relevant factory, prompt, metadata, role contract re-export, toolset, procedural skill, native runner, and frozen evaluation before changing role behavior. Keep the public packet outcome-blind and keep labels/oracles external.
2. Make the smallest role-local change. Add a procedural skill only for reusable guidance; do not add scripts, assets, code execution, mutable state, remote loading, or a placeholder policy/registry. If a contract changes, update actual consumers rather than creating a duplicate documentation or compatibility schema.
3. For any skill content or capability change, qualify the new resource digest and capability identity and ensure the resource loads from an installed wheel outside the checkout. Record preloaded procedure names through the sanitized bounded accounting path; record unavailable usage or cost as unknown.
4. Run proportionate offline checks from the repository root:

   ```bash
   just check
   just -- test tests/unit/test_agents.py tests/unit/test_agent_evaluator.py
   ```

5. Run the affected frozen isolated evaluation with an explicitly configured worker/provider environment. The supported entry point is `just eval-agent`, described in [agent evaluations](evaluations.md). A deterministic native-ADK test double is useful for regression coverage but is not a live-model result.
6. If a change reaches composition, retain the separate Docker/Temporal/native-evidence and external-scoring result. Do not treat an isolated fixture result as evidence of target execution, security efficacy, or durable workflow behavior.

Nix and `uv.lock` pin the development tools and Python dependencies, but they do not make the full application/container path hermetic; Docker, the selected model service, and host state remain external. Supported developer targets are macOS arm64 and Linux amd64 only; consult the [platform reference](../reference/platforms.md) before making a platform claim.

## Core preload versus optional progressive loading

The required role procedure is parsed from its private packaged SKILL.md by native ADK during controlled factory assembly and its instruction body is present in LlmAgent.instruction before the first model request. This avoids relying on a structured-output model to choose a loading tool. Usage.skills_preloaded and agent.skill_preloaded describe actual preparation, not model compliance or tool execution. Neither role offers optional progressive loading any more (no `load_skill` or `load_skill_resource`), so Usage.skills_loaded is always empty; it is not rewritten as successful tool use.

The producer has no `SkillToolset`: a reload returned the same text, spent a model call and kept about 1.7 KB of tool response in every later request, and the toolset itself added ADK's generic "load the skill first" instruction and two loader declarations (about 3.3 KB) to every request. `uv run --locked python scripts/measure_producer_request.py` renders the producer's first request for the frozen producer rows through the production `run_producer` path with a capturing model (no provider call, no target execution) and reports bytes and a `ceil(bytes/4)` token approximation per part: the Corsair instruction, ADK-appended instruction, tool declarations, response schema, packet and conversation. `--structured-tools` measures the response-schema path. [`test_producer_request_size.py`](../../tests/unit/test_producer_request_size.py) pins the instruction and declaration byte bounds, every producer rule, and the absence of loader declarations and ADK skill text.

The auditor has no tools, so its review is one request. `uv run --locked python scripts/measure_auditor_request.py` renders that request for every frozen auditor row through the production `run_auditor` path with a capturing model and reports the same parts plus the episode's LLM and tool calls; by default it models the LiteLLM route (no schema-with-tools support), and `--structured-tools` the native Gemini one. With the former `SkillToolset` the system instruction plus tool declarations rendered 7,683 bytes on the LiteLLM route (6,806 natively), declared `set_model_response`, `load_skill` and `load_skill_resource`, and charged one `set_model_response` tool call; tool-free it renders 3,481 bytes on both routes, declares no tool and charges none. [`test_auditor_request_size.py`](../../tests/unit/test_auditor_request_size.py) pins that shape and byte bound.
