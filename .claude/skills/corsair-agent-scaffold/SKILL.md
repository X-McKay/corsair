---
name: corsair-agent-scaffold
description: Use when creating a Corsair agent, adding a model-facing tool or moving an agent package. Follow SPEC-0082, trusted native AgentSpec/Harness capabilities, typed domain boundaries and isolated evaluation; there is no generator.
---

# Corsair agent scaffold

Read `AGENTS.md` and SPEC-0082's Agents section. Use `corsair-development` and `corsair-review`. Inspect the current packages under `src/corsair/agents/`; do not copy retired v1 paths, role lists or migration plans.

## Add or change an agent

1. Confirm one objective and whether an existing role can own it. Define typed input/output, restricted tools, failure attribution and the frozen eval cases it must satisfy. Keep new behavior unwired until its isolated checks pass.
2. Follow the actual package shape: `agent.yaml`, `agent.py`, `tools.py`, `skills/` and `evals/`. Introduce subdirectories or shared helpers only for a demonstrated need; do not prescribe a new tool framework or base-class hierarchy.
3. Keep short static instructions and descriptive prompt/config version metadata in trusted package `agent.yaml`; keep procedure in owned `SKILL.md` files. Load a fixed package path with native `AgentSpec.from_file(...)` and `Agent.from_spec(...)`. Never load manifests or arbitrary capabilities from an investigated repository.
4. Pass the explicit native model, typed dependencies/output type, restricted Python capabilities, validators and resolved operator limits. Use the same factory for direct/isolated/durable callers. Verify actual Temporal registration and invocation before claiming durability; a constructor test alone is insufficient.
5. Use native Harness `Skills` for progressive disclosure, with a trusted read-only package library. Distinguish catalog selection from filesystem authority and workspaces from isolation. Verify the pinned APIs and first-request/catalog/activation behavior; do not implement another skill loader or enable unrestricted Coder/delegation defaults.
6. Keep source/probe validity, assigned write path, independent authors and outcome-blind review as code-enforced domain boundaries. Preserve root two-probe rules and the actual marker interface. A generic writable filesystem or shell capability is not a replacement for them.

## Add a tool and evaluate

1. Put a callable with typed arguments, concise description and bounded returned observations in the existing tool module. Register through the native toolset/capability used by that package; test exact offered tools, policies, refusal paths and limits.
2. Reuse explicit provider configuration and operator budgets; add no second credential resolver, silent fallback or investigated-repository policy authority. Record prompt/spec/skill/tool identities and effective settings; missing usage remains unknown.
3. Add frozen cases under `src/corsair/agents/<name>/evals/<language>/<set>/<case>/`, with agent-visible input separated from evaluator-only oracle. Reuse `evals.agent_eval.AgentEval` in the package's `evals/evaluate.py` entry point; `v2_suite()` in `evals/run.py` discovers it dynamically for known roles. A genuinely new role also needs the explicit role inventory updated, not a second static suite registry or separate harness.
4. Run affected unit tests and `make eval AGENT=<name> SET=<set> EVAL_LANGUAGE=<language>`. Compare the same model/input/limits/mode and retain failures. Scripted clean cases establish plumbing, not inference accuracy or native workspace qualification. Record missing suites/baselines explicitly.
5. For a move or native-capability migration, check before/after instruction/tool/schema/settings parity, then isolate changed behavior and evaluate before composing it. Preserve frozen histories and fixtures; do not rewrite them to make a score pass.
