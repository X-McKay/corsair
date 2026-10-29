# CLI presentation implementation plan

Status: implemented and verified on `codex/intake-code-quality`, preserving the uncommitted PLAN-0006 changes. Neither pass is committed or pushed.

**Goal:** Make intake-to-investigation progress and results clear in interactive terminals, narrow terminals and logs.

**Architecture:** Extend existing Rich views and native Temporal query observation. The CLI queries a parent's active investigation child; workflows only expose deterministic metadata. Execution, receipts, prompts and JSON result contracts retain their existing ownership and meaning.

**Tech stack:** Existing pinned Python, Rich, argparse and Temporal SDK. No new UI framework or dependency.

## Approved design and boundaries

Implement the first four recommendations approved in the conversation: unified stage/session/round progress and selected image; explicit completed/stopped/failed/detached end states with stale-query visibility; compact results with `--details`; responsive cards below 80 columns and wider tables above. Prefer this incremental Rich approach over a new full-screen TUI, which would add navigation and lifecycle complexity beyond this request.

Animations indicate active waiting only. Batch bars use actual counts. Retry rounds remain visible and no stage implies a security verdict. A cancelled local wait detaches from durable work. Render only code-owned text and allowlisted metadata. Keep JSON result bytes/fields independent of presentation flags, retain full identities in detailed and machine views, preserve `--no-animation`, `--no-color` and redirected output behavior. Unavailable evidence or status remains explicit.

## Tasks and interfaces

### 1. Native parent/child progress

- [x] Add failing tests for `query_intake_progress(client, handle) -> dict`, preserving parent identity/image/timing while exposing child phase/session/round and isolating child query failure.
- [x] Add deterministic parent status metadata in `workflows/intake_pipeline.py`; query the actual child through `adapters/temporal/client.py`. Wire connected CLI wait/watch paths. Handle old workers with absent optional metadata.
- [x] Verify parent stop/cancellation and replay behavior with workflow tests; no workflow I/O.

### 2. Animation lifecycle and freshness

- [x] Add tests for successful/stopped/failed/detached waits, status loss and recovery, and JSON silence.
- [x] Extend `entrypoints/terminal.py` and `render/progress.py` with a local presentation state, last successful query time, non-spinning end frame and narrow layout. Final state comes from typed results or observed failure, never a guessed security conclusion.
- [x] Verify deterministic rendering and a real pseudo-terminal lifecycle including Ctrl+C.

### 3. Compact, responsive results

- [x] Add tests that compact output retains verdict/scope/selected image/next action while hiding long tables, `--details` restores details, and JSON is identical across flags.
- [x] Extend existing `render/result.py`, `render/intake.py`, `render/runs.py` and shared formatting; thread the presentation option through the CLI/Terminal. Parent summaries display a bound local child receipt when available and explicitly retain missing/unavailable state.
- [x] Verify at 48, 80 and 120 columns, including long IDs, stopped parents and model-text sentinels.

### 4. Delivery

- [x] Update CLI/monitoring guidance and architecture ownership.
- [x] Run affected tests, `just check`, full offline suite, real Temporal/replay and native CLI/pseudo-terminal checks; build and load the wheel outside the checkout.
- [x] Fresh read-only review; resolve material findings with regressions; record results and remaining qualification limits.

## Review focus

Child query failure must not erase known parent state. Local cancellation must not cancel durable work. A returned error/stopped result must not get a success badge. Long metadata must remain readable at narrow widths. Machine output must stay complete and free of animation or model-text leakage into human summaries.

## Execution notes

Inline implementation follows the approved scope without another confirmation round. This plan is the persistent task ledger in the repository's required location; any disposable artifacts belong under ignored `.work`. Existing quality changes remain uncommitted, and this pass will not push or merge. Run tests before and after each behavior change and use one fresh final review.

## Implemented behavior and review

- Native queries follow the active child and preserve the parent's image/time budget. Parent snapshots are rendered as status, not parsed as incomplete result receipts. Unknown status metadata is excluded from human views.
- Completed/stopped/failed/cancelled/incomplete frames follow typed results; local interruption shows detached and a reconnect command. Lost queries retain known state, show freshness and recover visibly. A failed first query explicitly says no status has been received.
- Compact summaries retain verdict/scope/image/next command. `--details` restores full hashes, round gates, recorded timings and usage. Narrow round and run views use cards. Parent views load only the exact committed child matching identity, case, disposition and execution status; unavailable child evidence cannot imply a verdict.
- Review found two recovery gaps: generated commands dropped custom settings, and standalone intake lacked online inspection. Both now have regression coverage: commands retain shell-quoted settings paths, and standalone intake uses typed native waiting without a status query. Follow-up review found no remaining issues.
- Native query/cancellation coverage exposed a parent race: a cancelled child can surface as `ChildWorkflowError`. The parent now preserves observed cancellation before classifying a child error as uncertain. Execution scheduling, evidence, image selection, prompts and receipt contracts are unchanged.

## Verification record (2026-10-29, macOS arm64 / Colima)

The initial 12 presentation regressions failed before implementation. Subsequent checks caught detailed-table tests needing the explicit flag, an eager import of Docker from saved-report rendering (fixed by lazy loading), and animated tests that needed an interactive terminal environment. Review regressions failed 3/3 before the recovery fixes. A first-query freshness regression also failed before its correction.

The first native run was **37 passed / 4 failed**: cancellation attribution, a doctor test using unbuilt default language images, its obsolete aggregate Docker-check assertion, and a PTY assertion that ignored wrapping. Tests now use an explicit Python image configuration and per-image diagnostics. Production doctor behavior was not weakened. The corrected rerun was:

```text
nix develop --command env TMPDIR=/Users/al/git/corsair/.work/tmp \
  CORSAIR_TEST_DOCKER=1 CORSAIR_TEST_TEMPORAL=1 uv run --locked pytest -q -W error \
  tests/workflow/test_intake_pipeline_workflow.py tests/integration/test_cli.py \
  tests/integration/test_intake_pipeline_chain.py tests/replay -m 'not live'
41 passed in 150.91s

nix develop --command env TMPDIR=/Users/al/git/corsair/.work/tmp \
  CORSAIR_TEST_TEMPORAL=1 uv run --locked pytest -q -W error \
  tests/workflow/test_agent_intake_workflow.py -k source_failure
1 passed, 1 deselected in 0.29s
```

The native cohort includes the final frozen case01 pipeline with scripted ADK outputs, real Docker evidence, real Temporal children, selected-image binding and categorical stops. It also checks actual console processes, status queries, JSON/plain/PTY Ctrl+C detachment and history replay. The additional standalone intake test reconnects through a real client and verifies the typed result. These checks do not establish live-model accuracy or cross-platform behavior. No model/provider, prompt, oracle, frozen fixture or permission changes were made; no live-model evaluation was repeated for this presentation pass. PLAN-0006's live results and ISSUE-0001 remain separate historical qualifications and limits.

Final offline/package gates:

```text
nix develop --command just -- test -q -W error
1221 passed, 137 deselected in 26.71s
Includes building/installing the wheel and loading packaged resources outside the checkout.

nix develop --command just check
Pinned Ruff lint/format, ty with warnings as errors, toolchain and local docs checks passed.

nix develop --command just build
Built dist/corsair-0.1.0.tar.gz and dist/corsair-0.1.0-py3-none-any.whl.
```

Archive inspection checks exclude private state, caches, credential filenames and bytecode. The build retains the pre-existing uv/uv-build version-range warning. Frozen datasets, fixtures and baselines have no diff. No publication or broader model/runtime qualification is claimed.
