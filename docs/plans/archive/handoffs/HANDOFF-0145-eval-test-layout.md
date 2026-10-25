---
id: HANDOFF-0145
kind: handoff
title: Strict evaluation and test category layout
status: implemented
updated: 2026-10-25
related: [PLAN-0113, HANDOFF-0144, ISSUE-0010]
---

# Evaluation and test layout

## Scope and state

The user requested exactly five evaluation directories and five test categories. The local working tree at `/Users/al/git/corsair` remains on `manus/just`; earlier implementation/documentation work and original-main stash `0ce65a61` were preserved. No commit, push, PR update, deployment or release was performed. See [current work](../../README.md) and [PLAN-0113](../plans/PLAN-0113-eval-test-layout.md).

```text
evals/                      tests/
  datasets/                   unit/
  evaluators/                 integration/
  experiments/                workflow/
  fixtures/                   replay/
  baselines/                  security/
```

Root tests/__init__.py and conftest.py remain standard package/discovery files, not extra category directories. Obsolete ignored bytecode-only folders were removed after checking their actual contents. Future transient Python caches remain ignored generated artifacts, not components.

## Implementation

- Moved tests/fixtures/adk.py to [tests/unit/adk.py](../../../../tests/unit/adk.py) and tests/fixtures/temporal.py to [tests/workflow/temporal.py](../../../../tests/workflow/temporal.py), preserving both files byte-for-byte.
- Updated pytest plugin registration and integration/workflow/replay imports. Removed only the former docstring-only package initializer; no compatibility package remains.
- Replaced test_agents.py's custom importlib file loader with an ordinary typed import. AST comparison confirms every pre-existing test/helper function and class is unchanged apart from helper import module paths.
- Added [evals/evaluators guidance](../../../../evals/evaluators/README.md) pointing to the existing installed evaluator/scorer. No implementation copy, launcher stub or new oracle was introduced.
- Updated testing guidance and repository ownership instructions. Runtime source/resources and SDK/Nix/dependency pins did not change.

## Verification

Collection before/after has134 identical node IDs in identical order. All29 original evaluation files—including frozen datasets, inputs, target sources, oracles, baselines and experiment records—are byte-identical. Production frozen loaders independently validated3 whole-system cases and3 isolated fixture cases without inference.

Pinned quality gates passed twice: Ruff lint, Ruff formatting, Just formatting and ty with warnings treated as errors. Offline tests passed103 with31 deselected before final cleanup; final retest passed103 with31 deselected in25.92s. Fresh sdist and wheel built; the existing uv0.13.4/uv-build range warning remains visible, with pins unchanged.

The complete non-live native suite passed **133 tests,1 deselected,0 skipped** in156.31s. It used real Docker/Colima, native ADK scripted model doubles and SDK-owned temporary Temporal servers. The1 deselected test is the live-provider smoke: no provider settings, credentials or live inference were used. This verifies the moved native consumers, not model accuracy. Current live behavior still has [ISSUE-0010](../../active/ISSUE-0010-live-safe-case-probe.md) and the earlier2/3 composed model batch.

Docker cleanup inspection found zero containers labelled corsair.security=true. SDK fixture teardown awaited environment.shutdown and the successful native session exited. A separate global process-table check was denied by local ps policy; independent OS-level server-process absence is therefore not claimed. No broad permission escalation or unrelated-service cleanup was attempted.

## Preserved attempts and delivery

The first safety assertion stopped after helper moves because the former initializer contained a docstring rather than being empty. Inspection confirmed it had no behavior; the partial move was completed without repeating moves. Discovery then exposed the legacy file-based fixture path, which was replaced with a normal import. A local SDK network-bind restriction during collection required explicit IPC/network permission. An overbroad scan also matched the trusted driver's legitimate target loading; it was narrowed rather than changing runtime behavior to obtain a pass. Final discovery, quality and native checks supersede these failed attempts.

Sanitized reports and the checked current-working-tree source archive are under outputs/eval-test-layout-20261025. Private test logs, hashes and checkpoints remain under .work/eval-test-layout-20261025. The source package excludes caches, old test helper paths, credentials, .git, .runs, .state and private diagnostics; it includes prior uncommitted implementation and current documentation. A manifest and SHA-256 receipt identify its exact files. No frozen baseline was silently re-promoted and no historical failed result was discarded.
