---
name: corsair-agent-scaffold
description: Use when creating a new Corsair agent, adding a model-facing tool to an agent, or moving an existing agent package to the standard layout. Follows docs/agent-packages.md; there is no generator.
---

# Corsair agent scaffold

Read [the agent package convention](../../../docs/agent-packages.md) first; it is authoritative and this skill does not repeat it. Use `corsair-development` for records and `corsair-review` before finishing. This skill grants no tools, approves no graph integration and certifies nothing.

## New agent

1. Confirm the objective is a new role rather than a change to an existing agent. Write its spec: typed input and outcomes, narrow ports, authority, failure layers and the frozen eval set it ships with.
2. Create only the files whose responsibilities exist, following the layout. Start from the environment agent (`src/corsair/agents/environment/`) as the reference.
3. Put each model-facing tool in `tools/<tool_name>.py` and register it in `tools/toolset.py`; export `TOOLSET_SHA256` and pin it in a toolset test that also checks exact names, order, id and retries.
4. Unimplemented behaviour must fail clearly. Never return a fabricated `ready` or register an unfinished tool. The agent starts unwired from any chain or workflow.
5. Add the eval set under `evals/<role>/`, write `toolset_sha256` to its `configuration.json`, add a `SUITES` entry in `evals/run.py`, and run `make eval AGENT=<role>` scripted. Model-written code is never executed on the host.

## New tool on an existing agent

1. Add `tools/<tool_name>.py` with the callable, annotated arguments, docstring description and returned observation model.
2. Register it in `tools/toolset.py` in the intended offered position. Update the toolset test's names and pinned digest in the same change, and say why the model should be offered it.
3. Run the agent's tests and `make eval AGENT=<role>`; report the `toolset_sha256` change and any score change against the baseline.

## Moving an existing agent

Follow "Moving an agent to the convention" in the convention document. The move must not change what the model is offered: capture before and after, require byte equality, and compare `make eval` runs. Do not move a package another open PR is changing; wait for it to merge.
