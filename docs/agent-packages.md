# Agent package convention

Every agent under `src/corsair/agents/<role>/` places the same responsibilities in the same files, so a reader, reviewer or new agent knows where each piece lives. Accepted under [IDEA-0006](development/ideas/IDEA-0006-agent-package-convention-and-scaffolding.md) and specified by [SPEC-0052](development/specs/SPEC-0052-environment-agent-package-convention.md). The current native-spec migration is tracked in [SPEC-0080](development/specs/SPEC-0080-native-agent-manifests.md) and [PLAN-0095](development/plans/PLAN-0095-native-agent-manifests.md). All seven current factory variants use package manifests; the accepted PR132 amendment removes custom construction and capability selection, while further agents follow it under [PLAN-0056](development/plans/PLAN-0056-agent-package-convention.md), preserving behaviour.

This is a responsibility convention, not a file generator or base class. Create a file only when its responsibility exists: a tool-free agent has no `tools/`, and an agent with no stage-specific dependencies beyond its input has no `dependencies.py`.

## Layout

```text
src/corsair/agents/<role>/
  __init__.py          small explicit public exports
  agent.yaml           trusted native name/description/literal instructions and narrow metadata
  agent.py             explicit native construction and Python capability instances
  contracts.py         vendor-free typed inputs, drafts, results
  dependencies.py      injected ports, operator-owned budgets, trusted per-run state
  prompts.py           typed-input rendering and compatible exports of manifest/skill identity
  validation.py        trusted output function (draft admission and finalization)
  tools/
    __init__.py        exports the toolset builder, digest and tool constants
    toolset.py         explicit registration in offered order, plus the toolset digest
    <tool_name>.py     one module per model-facing tool, named after the offered tool
  skills/<skill-id>/SKILL.md
evals/<role>/          frozen cases and evaluator-only oracles (SPEC-0044)
tests/agents/          contract, factory, toolset and evaluator tests
```

Domain helpers keep meaningful names (`frameworks.py`, `static.py`) rather than collecting in `utils.py`.

## Responsibilities

- `agent.yaml` owns the role's static boundary instructions once. The supported envelope is native `name`, `description`, literal `instructions`, plus restricted metadata `config_version`, `prompt_version`. Do not place models, settings, schemas, ports, tools, retries, policy paths or arbitrary import strings in it. Referenced procedure stays in `skills/`; Python explicitly instantiates admitted capabilities.
- `agent.py` assembles the explicit model, dependencies type, admitted capability instances/toolsets, trusted output function, retries, instrumentation and optional native durability through native `Agent.from_spec(...)`. It holds no domain logic and re-exports moved names its callers already import.
- `contracts.py` holds typed data and intrinsic invariants; no SDK objects, run context or I/O.
- `dependencies.py` holds the narrow ports the agent receives, operator-owned budgets the model cannot change, and per-run state the trusted finalizer reads. Concrete adapters are selected outside the package.
- `prompts.py` renders the request from typed input only, exports versions/identity from the package spec and procedure text from its owned skill files, and does not duplicate the manifest's static instructions: no labels or oracles, no workspace discovery, no external calls. Skill text is read as UTF-8 and its SHA-256 is exported for run identity.
- `validation.py` admits or refuses a draft against what this run actually observed, using `RunContext` and bounded `ModelRetry`. Stage behaviour stays distinct; there is no shared finalizer or repair loop.
- `tools/<tool_name>.py` owns one tool's callable, argument annotations and descriptions, tool-specific validation and the observation model it returns. Shared source readers and runners are reused from their packages, not copied.
- `tools/toolset.py` registers each tool explicitly with `FunctionToolset.add_function(..., name=..., retries=...)` under a stable toolset id. Adding a module offers nothing until it is registered here; there is no directory scanning, plugin loading or import-string registry.

## Identity

`tools/toolset.py` exports `TOOLSET_SHA256`, computed by the shared `corsair.agents.toolset_identity.toolset_sha256`: the SHA-256 of the toolset id and, in offered order, every field of each native tool definition plus its retry limit. The agent's eval suite writes it to `configuration.json` as `toolset_sha256`, and `make eval` lists it with the prompt, config and skill identity in `summary.json` and `comparison.md` (SPEC-0044). A toolset test pins the digest, so any change to what the model is offered is a deliberate, reviewed change to that test.

An agent offered more than one toolset (authoring: source reads, then writes and runs) exports one digest over all of them in offered order (`toolsets_sha256`). A toolset wrapped by a native `PrepareTools`-style rule (repository identification withdraws its tools when the byte budget is spent) is digested with the wrapper type and the rule's qualified name. An agent with two source modes (identification: inline files and a saved repository) keeps one factory, config version and digest per mode in the same package.

## Trusted native spec and operator policy

Each factory calls native `AgentSpec.from_file(...)` on its fixed trusted package path and `Agent.from_spec(...)` with explicit Python model, dependencies/output validator, capability instances, retries, validation context and optional native `TemporalDurability`. YAML contains native name/description/literal instructions and descriptive `metadata` with `config_version`/`prompt_version`; it contains no capability selector or import strings. Tool authority and the offered capability order remain explicit Python. `factory_identity` is a provenance-only file-hash helper, not a loader, selector or construction framework. Investigated-repository manifests are never discovered or used.

Keep the full package structure and design around the pinned out-of-box PydanticAI APIs. SDK-agnostic exploration is deferred; no generic SDK schema or Google adapter is part of this amendment. Skills remain owned files; native Harness Skills now supplies directory discovery and deferred model disclosure. Explicit role toolsets are separate from the instruction-only skills.

The manifest owns literal static instructions; skill files own procedures; Python owns contracts, validators, tool authority and durability. Preserve complete rendered instructions/capabilities before and after migration, including meaningful whitespace and order. Compatibility exports may read these owned sources but must not create a second instruction truth.

Operator model configuration remains explicit: `load_inference(path)` validates JSON or YAML through the same `InferenceConfig`, with legacy JSON provider compatibility. Packaged `policy/model.yaml` is an inert example, not an automatic provider or fallback. Trusted `policy/budget.yaml` supplies validated defaults; `corsair.policy.budget.load_budget(path)` accepts that default or an explicit operator-owned flat `CompositionBudget` override. Request settings, run ceilings, retries and input-derived effective allowances remain separate native controls. Investigated source cannot choose active agent manifests or mutate these policies.

Receipts distinguish the manifest digest (`spec_sha256`), skill/tool/factory identities, selected model-policy file/resolved configuration and packaged/effective budget digests. Record effective limits/retries as well as named profiles. Direct, durable and isolated modes must resolve the same admitted values. A native loader, YAML presence or parity test does not qualify an agent/provider/runtime.

## Moving an agent to the convention

1. Capture what the agent offers the model before the move: instructions, rendered prompt, tool definitions in order, output tools, toolset id and retries (a `FunctionModel` that records `AgentInfo`).
2. Split the package; keep public imports working from their old modules.
3. Show the capture is byte-identical after the move, pin the toolset digest in a toolset test, and run the agent's offline tests.
4. Run the role's isolated eval before and after with identical inputs/provider/settings. Preserve the original run; new manifest/policy/factory identities identify the migrated run. Separate body review, assertion metadata and native execution qualification.
5. Record both runs, complete instruction/tool/schema/settings/limit parity and any unknown telemetry in the agent's plan. Retain saved histories and check direct/durable parity and appropriate replay without rewriting historical evidence.

The shared [`corsair-agent-scaffold`](../.claude/skills/corsair-agent-scaffold/SKILL.md) skill walks through creating an agent or adding a tool against this convention. There is no generator; IDEA-0006 section F waits until a new agent needs one.

## Native skill disclosure

PydanticAI Harness provides `Skills` for standard `SKILL.md` directory discovery and progressive disclosure: the initial catalog contains names/descriptions and the native `load_capability` tool activates a body. Prefer this upstream capability over a Corsair skill registry or loader. See [native Skills](https://pydantic.dev/docs/ai/harness/skills/). This is a separate `pydantic-ai-harness[skills]` dependency; Harness0.55.0 is pinned alongside its exact required core2.55.0. All seven factories attach a read-only primary package LocalWorkspace and native Skills with explicit role-library selections. Source content stays in the existing typed ports; no FileSystem or Shell tools are attached by this change. Native body delivery is tested; live model quality and service replay remain separate qualification gates.

The documented `Skills` capability does not itself read bundled references or execute scripts. Skill catalogs, resource reads and tool authority are distinct. Configure only trusted package skill libraries; retain existing restricted tools and mandatory budget/output validation. Check skill activation, additional native tool calls, current-run history/validator compatibility, effective limits and direct/durable fixture behavior before changing a role. A second SDK adapter or bespoke skill-loading framework is not part of this direction.

## Harness reuse review

Corsair uses PydanticAI core, native Harness Skills and native Temporal integration. Prefer evaluating individual [Harness capabilities](https://pydantic.dev/docs/ai/harness/coder/#composition) before writing another common agent utility. `Coder` composes filesystem, shell, repository context, subagents and context-management capabilities; its default surface is broader than the current source-only authors and frozen-evidence assessor. Candidate reuse: Skills across roles; restricted FileSystem for source/planning reads and own-file authoring; Shell only through an admitted preparation/execution workspace; context/argument handling only after receipt and validator checks. An SDK workspace is not itself proof of sandbox qualification.

Do not silently activate full Coder, repository instructions from investigated code, delegation or shell in source-only agents. Native capability reuse must retain exact source/patch identities, separate control/exploit inputs, both native outcomes, outcome-blind review and operator budgets. Preserve SDK defaults deliberately: bounded output truncation, tool-result clearing and tool retries can change what validators observe. Qualify the relevant capability and workspace against existing ports/evals before replacement; a blanket ban on Harness is not intended.
