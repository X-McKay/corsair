---
id: PLAN-0065
kind: plan
title: Runtime selection as the chain's first stage
status: in_progress
updated: 2026-10-13
related: [SPEC-0060, SPEC-0042, PLAN-0046, SPEC-0035]
---

# Runtime selection as the chain's first stage

## Objective and dependencies

Implement [SPEC-0060](../specs/SPEC-0060-chain-runtime-selection.md) from main `4efad96`. Depends only on merged work (SPEC-0042 detector, matrix and hand-off; SPEC-0035 durable chain). Independent of the held PRs: it does not touch the identification, planning or authoring packages (#49, #44, cascade) and adds no matrix row (#51, #55, #65, #67, #68). No kind cluster or model server is needed.

## Steps

- [x] `RuntimeInputs`, `RuntimeOutcome`, `RuntimeCatalog`, `runtime_outcome` and `select_runtime`; `environment_input` built on the shared decision; unit tests.
- [x] `run_chain` runtime stage with the `RuntimeSelector` port, identity check and limitation; `run_direct(catalog=)`; direct-mode tests.
- [x] Durable: `select_runtime` activity, catalog in `configure_chain`/`run_durable`, `ChainResult.runtime`; payload round-trip tests; native Temporal stop test.
- [x] `make test-config`, `make eval AGENT=chain`, `make eval AGENT=environment`; review; CURRENT.md row; handoff.

## Validation and progress

All in this cloud container, 2026-10-13, no cluster or model server:

- Baseline before the change: `make test-config` 1238 passed (main `a459ced`/`4efad96`).
- `make test-config` with the change: 1258 passed; after merging main `759b016` (#55): 1287 passed; after merging main `93a0fab` (#51, JDK 8 and JUnit rows): 1290 passed and the native chain file 10/10; after merging main `af4d22d` (#49, #65, #67): 1369 passed, native chain file 10/10, scripted chain 5/5; after merging main `311d8cd` (#68, #44): 1393 passed, native 10/10, chain 5/5; after `497db9f` (#74): 1393 passed; after `462306a` (#82 package moves): 1397 passed, native 10/10, chain 5/5, environment 16/16.
- Native Temporal (`tests/temporal/test_chain_native.py`) against a local `temporal server start-dev` (CLI 1.4.1, server 1.28.0, fetched from the GitHub release because the SDK's own download host is blocked here): 10 passed with the change, including the new durable runtime stop for `unsupported` and for a worker without a catalog (one `corsair.chain.select_runtime` activity, maximum attempts 1, no child workflow, no workspace). The first run failed 1 of 10: the no-catalog reasons differed between modes (`ValueError` in direct, `RuntimeCatalogMissing` durable); both modes now raise the `RuntimeCatalogMissing` kind with one message. On main the same file passes 8/8; the 12 and 14 sandbox pass-through warnings are the same per test.
- `make eval AGENT=chain` (scripted, fixture set): 5/5 clean on the branch and 5/5 on main `4efad96`; summaries differ only in the scripted assessment input token estimate (14,337.5 on main, 14,309.5 here), inferred to be the evidence path length (the main run was in a longer scratch path), not a prompt change.
- `make eval AGENT=environment` (scripted, development set): 16/16 clean; the agent package is untouched.
- Unrun: live chain or environment runs (need the model server, kind cluster and an environment stage); no frozen eval case carries build files yet, so the scripted chain eval exercises only the declared-environment path.

## Decisions and next action

Defaults chosen where the work forked (SPEC-0060): baseline-revision build files only; `not_prepared` kept apart from `unsupported`; the operator's declared identity must name the selected image. Next after this plan: the environment stage in the chain (G12). Merge order (Al's review of `993de00`): #63 also edits `nodes/runtime/environment.py` (structured blockers on `RuntimeStop`); whichever lands second carries those blockers into `RuntimeOutcome` and keeps both test sets. The handoff was renumbered HANDOFF-0090 because #70 uses HANDOFF-0083.
