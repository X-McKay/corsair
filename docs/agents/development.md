# Developing agent roles

Change an agent as one bounded component: keep its objective, typed contract, tools, prompt, native factory, and isolated evaluation aligned. The two roles are not a platform for adding general agents, provider wrappers, tool catalogs, or automated repair behavior. Architectural ownership is in the [architecture overview](../architecture/overview.md); active work is indexed in the [plans](../plans/README.md).

## Authoritative implementation locations

| Concern | Canonical location | Change boundary |
| --- | --- | --- |
| Producer behavior | [`src/corsair/agents/producer/`](../../src/corsair/agents/producer/) | Prompt, exact two source-read tools, and `Submission` factory configuration. |
| Auditor behavior | [`src/corsair/agents/auditor/`](../../src/corsair/agents/auditor/) | Prompt, tool-free factory configuration, and `AuditResult` output. |
| Role metadata and packaged prompts | [`src/corsair/agents/resources.py`](../../src/corsair/agents/resources.py) and each role's `agent.json`/`instructions/system.md` | Metadata is validated against the factory's exact tool names, instruction resource, and schema reference. |
| Wire contracts | [`src/corsair/contracts/agents.py`](../../src/corsair/contracts/agents.py) | Define or change a Pydantic model once; consumers import the canonical export. |
| Native episodes | [`src/corsair/adapters/inference/adk.py`](../../src/corsair/adapters/inference/adk.py) | Fresh ADK runner, callbacks, accounting, packet construction, and output validation. |
| Isolated evaluation and scoring | [`src/corsair/evaluation/`](../../src/corsair/evaluation/) | Frozen fixture loading, agent invocation, and external scoring. |

The runtime loads the role-local packaged prompt and JSON metadata through Python package resources. That is a narrow implementation detail, not a runtime skill system. Development guides and contributor instructions may explain how to edit the code, but they do not become model context, install directories, or grant an agent a capability.

## Preserve these role invariants

- The producer is restricted to data-only payload proposals and receives exactly `read_file` and `list_files`; the auditor remains fresh-context, tool-free, and outcome-blind.
- Factories use native `LlmAgent.output_schema` with canonical `Submission` or `AuditResult`. Do not reintroduce a custom `submit` function, termination state, string decoder, or schema-repair layer.
- Model capability determines whether ADK can combine schema output and ordinary tools directly or uses its own schema-completion fallback. Keep native callbacks, call/output/tool budgets, and post-generation Pydantic plus round/parent validation in force for both paths.
- Provider credentials stay in the worker environment. A model setting selects the native Gemini or LiteLLM route; it is not a credential broker or an invitation to add provider-specific placeholders.
- The model episode is an ordinary bounded Temporal activity. Do not substitute an upstream Google ADK Temporal integration, invent an agent graph, or add an implicit retry/fallback loop.

The producer's snapshot reader, the Docker sandbox, evidence verifier, artifact store, and final policy belong to trusted components. They must not be moved into an agent prompt or tool surface to make an evaluation pass.

## Focused change loop

1. Read the relevant factory, prompt, metadata, contract, native runner, and frozen evaluation before changing role behavior. Keep the public packet outcome-blind and keep labels/oracles external.
2. Make the smallest role-local change. If a contract changes, update actual consumers rather than creating a duplicate documentation or compatibility schema.
3. Run proportionate offline checks from the repository root:

   ```bash
   just check
   just -- test tests/unit/test_agents.py tests/unit/test_agent_evaluator.py
   ```

4. Run the affected frozen isolated evaluation with an explicitly configured worker/provider environment. The supported entry point is `just eval-agent`, described in [agent evaluations](evaluations.md). A deterministic native-ADK test double is useful for regression coverage but is not a live-model result.
5. If a change reaches composition, retain the separate Docker/Temporal/native-evidence and external-scoring result. Do not treat an isolated fixture result as evidence of target execution, security efficacy, or durable workflow behavior.

Nix and `uv.lock` pin the development tools and Python dependencies, but they do not make the full application/container path hermetic; Docker, the selected model service, and host state remain external. Supported developer targets are macOS arm64 and Linux amd64 only; consult the [platform reference](../reference/platforms.md) before making a platform claim.
