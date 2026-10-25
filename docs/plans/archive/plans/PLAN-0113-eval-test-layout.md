---
id: PLAN-0113
kind: plan
title: Align evals and tests with the requested category layout
status: implemented
updated: 2026-10-25
---

# Evaluation and test layout

Keep exactly the requested top-level directories under evals (datasets, evaluators, experiments, fixtures, baselines) and tests (unit, integration, workflow, replay, security), with standard root pytest/package files retained. Prior working-tree changes and stash are preserved. Most unsupported folders are ignored bytecode-only remnants of the retired implementation; inspect before deleting them.

Move the real ADK helper to tests/unit/adk.py and the Temporal plugin/helpers to tests/workflow/temporal.py. Update all consumers and root plugin registration, without changing test assertions or helper behavior. Preserve134 collected node IDs and all frozen datasets, fixtures and baseline bytes. Keep the installed evaluator/scorer implementations canonical; evals/evaluators documents their roles/commands rather than duplicating code or adding a compatibility wrapper.

Validate Ruff/format/ty, before/after collection equality, frozen loaders/hashes, offline tests and affected real Temporal tests where admitted. No provider settings or model calls are needed for this filesystem/import-only change. Finish with cleanup, retest, build and package; report native gates unrun/skipped rather than counting them as passes.


## Implementation and observed checks

Removed ignored bytecode-only legacy directories. Moved both helper modules byte-for-byte; removed the docstring-only former package initializer; updated root pytest plugin and consumers. Replaced the remaining dynamic file loader in test_agents.py with an ordinary typed import. AST comparison confirms every pre-existing test/helper function/class body is unchanged apart from helper import module paths. All29 original eval files—including datasets, fixtures, baselines and experiment records—remain byte-identical. Frozen loaders verified3 whole-system cases and3 isolated fixture cases without inference.

Full collection is unchanged at134 identical node IDs in the same order. Pinned Ruff/format/ty and the offline suite passed (103 passed,31 deselected). A final post-cleanup quality/offline/build run and actual Docker/SDK-managed Temporal non-live suite are in progress; their final results must be recorded before closure. No provider configuration or live model invocation is needed.

Preserved attempts: a safety assertion initially stopped after moving helper files because the package initializer contained a docstring rather than being empty; inspection confirmed it was docstring-only and the partial move was completed. Discovery then exposed a legacy file-based ADK loader; it was replaced, not repaired with a compatibility shim. A local SDK network-bind restriction during collection required the explicit network/IPC capability for collection. An overbroad retired-import scan matched the trusted target driver's legitimate dynamic module load; the check was narrowed to stale fixture paths and dynamic loading in tests only. No runtime target loader was modified to satisfy that check.


## Final results

After cleanup: locked Ruff/format/Just/ty checks passed again; offline tests passed103 with31 deselected in25.92s; fresh sdist/wheel built with the existing uv/uv-build range warning retained. The complete non-live suite passed133 tests with1 live-provider test deselected in156.31s, using actual Colima Docker and SDK-owned temporary Temporal dev servers. No provider settings/model calls were used, and source/resource bytes and frozen data were unchanged. All134 test node IDs and their order are preserved.

Read-only Docker cleanup inspection found zero Corsair-labelled containers. Native Temporal fixture teardown awaited the SDK shutdown and the test session exited successfully; a separate process-table verification was blocked by local ps permissions, so that OS-level check remains unconfirmed rather than asserted. No attempt to broaden host permissions or modify unrelated services was made.

Final packaging includes the actual dirty working tree with the new category paths and without retired fixture modules, ignored caches, credentials or raw diagnostics. Existing branch/stash/pins are preserved; no commit/push/release/deployment is performed. See HANDOFF-0145 for final paths and verification.
