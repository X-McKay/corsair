---
id: HANDOFF-0090
kind: handoff
title: Runtime selection as the chain's first stage
status: recorded
updated: 2026-10-13
related: [SPEC-0060, PLAN-0065, SPEC-0042, IDEA-0005]
---

# Runtime selection as the chain's first stage

## Verified state

Branch `claude/chain-runtime-handoff-dtb1ut` from main `4efad96`, then main merged (see git). Delivered under [SPEC-0060](../specs/SPEC-0060-chain-runtime-selection.md):

- `RuntimeInputs` (baseline build files, base64 on the wire) and `RuntimeOutcome` (`supported`, `unsupported`, `undetermined`, `not_prepared`) in `nodes/runtime/contracts.py`;
- `RuntimeCatalog`, `runtime_outcome` and `select_runtime` in `nodes/runtime/environment.py`; `environment_input` now returns the shared outcome instead of `RuntimeStop`;
- `run_chain` runs the runtime stage first through a `RuntimeSelector` port; `run_direct(catalog=)`; durable activity `corsair.chain.select_runtime` with the catalog in `configure_chain`/`run_durable`; `DirectRun.runtime` and `ChainResult.runtime`; the fixture journal records the outcome;
- the operator's declared image digest and language must be the selected row's.

No agent package, prompt, toolset, matrix row or eval set changed. Nothing is live-qualified.

## Validation and blockers

See [PLAN-0065](../plans/PLAN-0065-chain-runtime-selection.md#validation-and-progress): `make test-config` 1258 passed; native Temporal chain file 10/10 against a local dev server; scripted chain 5/5 and environment 16/16. No blocker for this slice. A live run needs the environment stage first.

## Decisions and next steps

- Defaults (SPEC-0060): baseline build files only; `not_prepared` separate from `unsupported`; declared identity must name the selected image.
- Next bounded action: the environment stage in the chain (G12). For a supported outcome, build the agent input with `environment_input`, run the environment agent in a preparation sandbox of the selected prepared image, check it with `check_ready`, and map `ReadyEnvironment` to `EnvironmentEvidence` and an observed `EnvironmentIdentity`.
- A chain eval case with build files (supported and unsupported) belongs with that stage, as a new set version.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then SPEC-0060, PLAN-0065, SPEC-0042, SPEC-0029 and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. Specify and build the chain's environment stage (IDEA-0005 G12) on top of the runtime stage: environment_input for a supported outcome, the environment agent in a preparation sandbox of the selected prepared image, check_ready, and a ReadyEnvironment to EnvironmentEvidence/EnvironmentIdentity mapping, in direct and durable modes. Do not edit agent packages another open PR changes or add matrix rows. Run make test-config, the native Temporal chain tests and make eval AGENT=chain/environment, update records and CURRENT.md, and write a new handoff.
```
