# Agent package convention

Every agent under `src/corsair/agents/<role>/` places the same responsibilities in the same files, so a reader, reviewer or new agent knows where each piece lives. Accepted under [IDEA-0006](development/ideas/IDEA-0006-agent-package-convention-and-scaffolding.md) and specified by [SPEC-0052](development/specs/SPEC-0052-environment-agent-package-convention.md). The environment agent is the reference package; evidence assessment follows it; other agents move one at a time under [PLAN-0056](development/plans/PLAN-0056-agent-package-convention.md), preserving behaviour.

This is a responsibility convention, not a file generator or base class. Create a file only when its responsibility exists: a tool-free agent has no `tools/`, and an agent with no stage-specific dependencies beyond its input has no `dependencies.py`.

## Layout

```text
src/corsair/agents/<role>/
  __init__.py          small explicit public exports
  agent.py             native PydanticAI factory only
  contracts.py         vendor-free typed inputs, drafts, results
  dependencies.py      injected ports, operator-owned budgets, trusted per-run state
  prompts.py           instructions, prompt version, skill text and digest, typed-input rendering
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

- `agent.py` assembles model, dependencies type, instructions, skill capability, toolsets, trusted output function, retries and instrumentation. It holds no domain logic and re-exports moved names its callers already import.
- `contracts.py` holds typed data and intrinsic invariants; no SDK objects, run context or I/O.
- `dependencies.py` holds the narrow ports the agent receives, operator-owned budgets the model cannot change, and per-run state the trusted finalizer reads. Concrete adapters are selected outside the package.
- `prompts.py` renders the request from typed input only: no labels or oracles, no workspace discovery, no external calls. Skill text is read as UTF-8 and its SHA-256 is exported for run identity.
- `validation.py` admits or refuses a draft against what this run actually observed, using `RunContext` and bounded `ModelRetry`. Stage behaviour stays distinct; there is no shared finalizer or repair loop.
- `tools/<tool_name>.py` owns one tool's callable, argument annotations and descriptions, tool-specific validation and the observation model it returns. Shared source readers and runners are reused from their packages, not copied.
- `tools/toolset.py` registers each tool explicitly with `FunctionToolset.add_function(..., name=..., retries=...)` under a stable toolset id. Adding a module offers nothing until it is registered here; there is no directory scanning, plugin loading or import-string registry.

## Identity

`tools/toolset.py` exports `TOOLSET_SHA256`, computed by the shared `corsair.agents.toolset_identity.toolset_sha256`: the SHA-256 of the toolset id and, in offered order, every field of each native tool definition plus its retry limit. The agent's eval suite writes it to `configuration.json` as `toolset_sha256`, and `make eval` lists it with the prompt, config and skill identity in `summary.json` and `comparison.md` (SPEC-0044). A toolset test pins the digest, so any change to what the model is offered is a deliberate, reviewed change to that test.

No separate manifest or cross-mode receipt layer is added; IDEA-0006 section D waits for a second consumer.

## Moving an agent to the convention

1. Capture what the agent offers the model before the move: instructions, rendered prompt, tool definitions in order, output tools, toolset id and retries (a `FunctionModel` that records `AgentInfo`).
2. Split the package; keep public imports working from their old modules.
3. Show the capture is byte-identical after the move, pin the toolset digest in a toolset test, and run the agent's offline tests.
4. Run `make eval AGENT=<role>` before and after; the only identity change allowed is `toolset_sha256` appearing.
5. Record both runs and the capture result in the agent's plan.

The shared [`corsair-agent-scaffold`](../.claude/skills/corsair-agent-scaffold/SKILL.md) skill walks through creating an agent or adding a tool against this convention. There is no generator; IDEA-0006 section F waits until a new agent needs one.
