---
id: IDEA-0006
kind: idea
title: Standard agent packages, identity, receipts and shared scaffolding skill
status: accepted
updated: 2026-10-13
related: [IDEA-0002, IDEA-0004, SPEC-0023, SPEC-0044, PLAN-0048, SPEC-0052, PLAN-0056]
---

# Standard agent packages, identity, receipts and shared scaffolding skill

## Problem and evidence

The user requested a consistent framework for the files underneath each agent, explicitly selected a `tools/` directory with one file per model-facing tool, and requested a shared Claude/Codex skill that makes scaffolding a new agent straightforward. This record captures that direction and its implementation options. It does not implement a scaffold, skill, runtime refactor or new graph stage.

The discussion began with a repository review at `42a7273786a18ffaef0dbd005dfead12af83cbbf`; this documentation branch is based on current main `8606068f8e1792ca63636ff14c2f09c8c4317d1b`. Later agent improvements must be preserved rather than replaced with the older reviewed implementations. In particular, environment host evaluation now exists on this base; an isolated evaluator must not be described as missing solely because an older review said so.

The packages are already close to a common layout, but responsibilities differ:

- Planning combines dependency construction, instructions, prompt rendering, native tool preparation and output finalization in `src/corsair/agents/test_planning/agent.py`.
- Authoring has dependencies in `tools.py`, prompts/finalization in `agent.py`, and domain checks in `static.py`.
- Environment combines dependency context, budgets, command ledger, observation models and tool implementations in `tools.py`.
- Planning/authoring load their skill through `skills/__init__.py`; identification loads its skill in `identification.py`.
- `issue_analysis/` contains historical analyst/reviewer/sequence implementations alongside active identification variants.

Direct and durable composition already reuse the same `AGENTS` mapping and native factories. The opportunity is predictable package ownership and consistent identity/receipt projection, not replacing that reuse with a second framework. See the existing [architecture boundaries](../../architecture.md#agent-contracts), [native-first simplification idea](IDEA-0002-simplification-isolation-and-generality-review.md), and [isolated evaluation contract](../specs/SPEC-0044-isolated-agent-evaluation.md).

## Proposal and limits

### A. Standard package responsibilities

Use one package per semantic role. A typical tool-using agent has this target layout:

```text
src/corsair/agents/test_authoring/
  __init__.py
  agent.py
  contracts.py
  dependencies.py
  prompts.py
  validation.py
  spec.py
  tools/
    __init__.py
    toolset.py
    read_source.py
    write_test_file.py
    run_tests.py
  skills/
    write-native-tests/
      SKILL.md
```

The responsibilities are:

- `agent.py`: the explicit native PydanticAI factory assembling model, dependencies, instructions, tools, trusted output function, retries, instrumentation and optional native durability.
- `contracts.py`: vendor-free typed inputs, drafts, results and domain observations; intrinsic data invariants.
- `dependencies.py`: injected narrow ports, operator-owned budgets and explicitly owned per-run state. Concrete adapter selection stays outside the agent package.
- `prompts.py`: instructions, existing prompt version and pure typed-input request rendering; no labels/oracles, workspace discovery or external calls.
- `validation.py`: stage-specific, context-dependent draft admission and trusted finalization. SDK-facing `RunContext`/bounded `ModelRetry` may live here; domain contracts stay vendor-free.
- `spec.py`: implementation manifest/identity exports and supported variants/modes, derived from actual declarations. Factory callables are bound in operator-owned Python, not serialized import paths.
- `skills/`: trusted named skill resources with consistent UTF-8 loading and digest attribution. Skill metadata cannot grant tools or authority.
- `__init__.py`: explicit, small public exports, preserving supported existing factory/type imports.

This is a responsibility convention, not a requirement to generate empty files. A tool-free agent needs no unused `tools/` directory. Domain helpers such as static assertion checks or setup ledgers keep meaningful names rather than accumulating in generic `utils.py`. Preserve the existing source-checkout packaging model; wheel resource loading is a separate decision.

### B. One file per tool, explicit registration

Every model-facing domain tool has its own snake_case module under `tools/`, named after the offered tool. This applies even when the agent has only one tool. Each module owns its callable, argument annotations/descriptions, tool-specific validation and observation mapping, plus small private helpers.

`toolset.py` imports and registers exact functions using native `FunctionToolset`, with explicit tool names, stable toolset IDs, retries and preparation/availability rules. `__init__.py` exports supported builders. Existing distinct toolsets may remain distinct; file organization does not justify merging capability boundaries.

Adding a file does **not** expose a new tool. Registration, manifest identity and authority tests change explicitly. No directory scanning, dynamic plugin loading, import-time global tool registry or arbitrary import strings are introduced.

Dependencies and shared state remain in their named modules. Substantial internal preparation/helpers can use a clearly internal module such as `_preparation.py` and are never registered as tools. Trusted native output functions remain in `validation.py`, even if their transport is an SDK output tool; the one-file rule is for restricted domain tools.

Shared source readers, runners and artifact capabilities should be reused, not copied into each agent. An agent-local binding module may adapt authority or descriptions, or explicitly re-export an identical shared callable. Do not add wrappers just for symmetry if they change offered schemas or obscure attribution. Execution, source acquisition, policy, credentials, witnesses and cleanup stay in deterministic ports/adapters/nodes.

Mirror tool-specific tests where useful:

```text
tests/agents/test_authoring/
  test_contracts.py
  test_prompts.py
  test_validation.py
  test_factory.py
  tools/
    test_read_source.py
    test_write_test_file.py
    test_run_tests.py
    test_toolset.py
```

The toolset test checks exact names, schemas, IDs, retries, preparation and absence of undeclared tools. Reuse shared capability tests rather than copying them into every agent.

### C. Standard component surface, not a base class

Each component declares its typed input/results, existing native factory, prompt renderer, dependency constructor, restricted toolset builders, trusted finalizer, implementation manifest and isolated evaluator binding. Keep semantic type/factory names and localized registry typing; do not replace all public contracts with generic dictionaries.

Keep stage behavior distinct. Identification validates localization/source provenance; planning admits a two-test plan; authoring reconstructs actual writes and final-run/patch consistency; assessment admits frozen evidence citations. Standardization does not mean a universal finalizer, shared tool bundle, identical budgets, generic retry/repair loop or global conversation memory.

Use separate logical role and concrete variant identities. Inline and repository identification remain explicit variants with their own supported modes; no silent fallback. A later active `issue_identification/` package should be an additive migration with compatibility exports. Historical analyst/reviewer contracts and replay/evaluation records remain outside the active registry until retention decisions are made.

### D. Identity and redacted receipts

A small immutable manifest identifies stage/variant, existing prompt/config versions, instruction/skill digests, toolset/interface identities, contract identities and supported modes. Record source commit and dependency lock provenance alongside it. It is not a qualification certificate or authority mechanism.

Record effective run configuration separately: admitted model key/sanitized provider identity, budget, output-correction limits, provider mode (`scripted|live`), execution mode (`direct|durable`) and backend identity. A configuration filename alone is insufficient.

Project existing native/direct/durable observations into a common immutable receipt with run/invocation IDs, manifest/config identities, input/output artifact references, invocation status, original domain outcome, admitted/rejected status where applicable, timing basis, usage coverage, attributed failure and generated patch references. A correct `unsupported` plan is a completed invocation; generated code is not proof of sandbox delivery or execution; completed assessment is not a security verdict.

Use an allowlist projection, not raw message/dependency/exception dumps followed by best-effort redaction. Keep secrets, prompts, source/evidence contents and hidden reasoning out. Missing telemetry stays unknown, not zero. Hashes are not anonymization; receipts remain private by default.

Reuse immutable artifact storage and ignored `.runs` indexes. No new database or tracing service is needed. Initially export receipts from returned records. Do not perform receipt filesystem/network I/O in Temporal workflow code. Crash-resilient per-stage export, if later needed, is a separate idempotent activity/exporter; it never authorizes retries of model requests or sandbox commands. Preserve historical identities and replay compatibility rather than recomputing older identities from current files.

Evaluation fingerprints distinguish identical reruns, declared treatment changes and confounded comparisons. A prompt/skill/code/model experiment must be able to change its declared treatment while keeping dataset/evaluator/runtime and other controls stable. Do not reject every changed manifest or automatically promote baselines.

### E. Isolated tests/evaluation and registration

Keep runtime code, evaluation inputs/oracles and tests in parallel locations with consistent package keys:

```text
src/corsair/agents/<role>/
evals/<role>/
tests/agents/<role>/
```

Preserve existing `make eval` aliases and frozen dataset/held-out manifests. Evaluation cases and oracles stay outside runtime package resources and model-visible inputs. Each evaluator retains domain-specific scoring while sharing entry-point, identity, receipt and artifact conventions. Runtime results and promoted private baselines stay under ignored `.runs/`.

Isolated evaluator/component registration is separate from active chain registration. An importable factory, a scaffold or a passed structural check does not imply wiring, qualification or new authority. Temporal integration still requires explicit payload/model/tool registration, compatible histories, and affected direct/durable/replay checks.

### F. Developer scaffold and conformance commands

Proposed developer-only commands, **not present today**:

```shell
make agent-new AGENT=<snake_case_name> SKILL=<kebab-case-name> DRY_RUN=1
make agent-new AGENT=<snake_case_name> SKILL=<kebab-case-name>
make tool-new AGENT=<name> TOOL=<snake_case_tool> DRY_RUN=1
make agent-check AGENT=<name>
make eval AGENT=<registered-eval-alias>
```

Use a small repository-owned Python generator/template set, not another task runner or runtime framework. Validate names and destinations, refuse traversal/collisions and overwrites, show all files in dry-run, and report partial failures without deleting preexisting work.

Generate a tool-using or tool-free native factory skeleton, typed extension points, per-tool modules/tests, identity hooks and isolated evaluator starter. Unimplemented domain behavior must fail clearly; it must not return fabricated `ready`, register unfinished tools or claim qualified evaluation. New components default to explicitly unwired, least-authority status.

The developer supplies objective, domain contracts/outcomes, narrow ports, prompts, tools, trusted finalizer and meaningful frozen cases. A generator cannot supply those semantic decisions. `tool-new` may create a tool/test starter but does not register it automatically; print the required explicit registration and evaluation steps.

Conformance checks verify explicit bindings/resources, exact offered tool surface, unique aliases, contract dependency boundaries, manifest consistency, mode declarations and receipt/evaluator projection. Use focused tests/captured native requests; structural checks are not proof of semantic accuracy, model obedience, sandbox enforcement or live client discovery.

### G. Shared Claude/Codex scaffolding skill

Add a proposed development skill named **`corsair-agent-scaffold`** when the generator/convention implementation is selected. Follow the repository's existing [shared skill convention](../README.md#using-the-skills):

```text
.claude/skills/corsair-agent-scaffold/
  SKILL.md
  references/
    agent-package-convention.md   # Thin navigation to the authoritative convention/templates
.agents/skills/corsair-agent-scaffold
  -> ../../.claude/skills/corsair-agent-scaffold
```

The references directory is optional: do not copy the entire convention into two independently maintained files. One canonical `SKILL.md` serves both clients; Codex discovery uses the Git symlink. Proposed explicit invocation is `/corsair-agent-scaffold` in Claude Code and `$corsair-agent-scaffold` in Codex. These paths/invocations are not installed by this PR.

Its description should trigger when creating a Corsair agent, adding a tool or standardizing an existing agent package. The skill should:

1. Read root instructions/current records, inspect the working tree and define the role, typed boundaries and current authorization. Reuse an existing component when appropriate.
2. Consult the canonical package convention/templates and existing native capabilities; distinguish scaffolding from adding a graph stage.
3. Run the generator's dry-run; then generate within scope without overwrites. If the generator is not implemented, report that prerequisite rather than pretending the command exists or silently inventing a competing scaffold.
4. Guide implementation of contracts, prompts, dependencies, one-file-per-tool bindings, trusted finalizer, manifest and isolated evaluator. Keep concrete adapters, credentials and operator policy outside model authority.
5. Register the isolated component/evaluator explicitly; register each new tool in `toolset.py` with reviewed authority. Leave active graph/durable admission separate.
6. Run conformance, focused tests and scripted isolated evaluation; compare behavior against frozen baselines. Preserve missing/live/runtime checks as unrun or unknown. Never execute model-authored tests on the host.
7. Use existing development/review/handoff skills and records for review and continuation. Do not require all record types for every small tool edit or introduce another approval gate.

Prefer a thin skill that invokes deterministic repository tooling over embedding a second implementation in prose. Skill metadata does not grant tools, approve graph integration or certify qualification. Add it to the existing skill metadata/symlink guards and developer invocation guide when implemented. Test generator failures and negative cases in temporary directories; actual Claude/Codex discovery/invocation requires separate client smoke evidence, not merely a passing symlink check.

## Decision

**Accepted with changes (Al, 2026-10-13):** adopt, and if successful cascade across all agents. The selected variant: identity is a `toolset_sha256` field added to the SPEC-0044 run identity, not a new manifest/receipt layer (section D waits for a second consumer); the skill is a thin guide to the convention with no generator (section F waits for a new agent); the environment agent is the reference package instead of planning, because open PRs change every other agent. Specified by [SPEC-0052](../specs/SPEC-0052-environment-agent-package-convention.md), planned with the cascade in [PLAN-0056](../plans/PLAN-0056-agent-package-convention.md), convention in [agent-packages.md](../../agent-packages.md).

Original proposal text follows.

**Proposed implementation; user-selected direction recorded.** The user selected one file per tool and asked to capture the agent convention and shared scaffolding skill in an idea PR. This change records that direction only. It does not create a new agent, generator, skill, spec/plan, capability, runtime/profile, provider, baseline or live qualification.

Recommended implementation sequence:

1. Use planning as the reference package. It has a clear read-only dependency/tool/finalizer boundary. Preserve public imports, exact prompt/skill bytes, offered tool schemas/names, toolset IDs, retries, budgets, finalizer behavior, workflow/activity names and serialized payload compatibility. Keep later main improvements.
2. Add manifests and receipt projection around existing factories/records without changing domain behavior. Verify identity and redaction plus unknown usage/timing semantics.
3. Derive the generator and focused conformance tests from the proven reference layout. Implement the shared `corsair-agent-scaffold` skill as a thin guide to that tooling, with one canonical skill and Codex symlink.
4. Migrate remaining roles one at a time with compatibility imports and their existing isolated evaluation. Treat active identification/historical separation and direct-only variants explicitly. A file move can affect replay, so run affected construction/history checks.

Acceptance for the first implementation: no unintended prompt/tool/authority change; scaffold dry-run/collision/path refusal; unregistered tools remain unexposed; meaningful typed negative outcomes; isolated eval/receipt identity; no raw secrets/content in receipts; no workflow I/O; same canonical skill discoverable through both client paths. Actual client smoke and live/runtime qualification stay separate.

Next bounded action, if selected for implementation: write a focused spec/plan for the planning reference refactor and scaffold/skill, with exact compatibility tests. Do not migrate all agents, widen the graph, implement a new scheduler/provider protocol, alter two-test/witness/disposition semantics, or execute authored code on the host as part of this documentation proposal.
