---
id: HANDOFF-0142
kind: handoff
title: Physical Mac native qualification and Qwen producer blocker
status: recorded
updated: 2026-10-25
related: [PLAN-0109, ISSUE-0009, HANDOFF-0141]
---

> Historical record. Commands, counts and status describe the recorded revision, not the current working tree. See [current work](../../README.md) for current guidance.

# Physical Mac native qualification and Qwen producer blocker

## Verified local state

`/Users/al/git/corsair` is on `manus/just`, tracking origin at `80e2ff56431ecc8e24d771c306ee203772ddbc69`. Pulled with `git pull --ff-only`. Initial dirty main research work remains in stash `0ce65a613e3da90534c40e3683d7851a3992df4b`, unapplied. Original main HEAD was `666d4962de4b3ba29139013b4dca1f7646be7fec`. Do not pop that stash on this redesigned branch. Preserve current local qualification notes/test changes before switching back to main and applying the original stash.

Removed 148 untracked bytecode files and 55 empty src directories; every one of 44 tracked runtime source/resource files remained unchanged. SDK dependencies use isolated `.work/mac-e2e-20261025/venv`; the previous main `.venv` and ignored state/evidence are untouched.

## Qualified checks

Actual physical host: macOS 26.6.2 arm64, existing Colima Docker 29.5.2 arm64; locked native Nix tools, Python 3.12.15 and pinned SDKs. Final complete suite **120 passed in 140.75 seconds**, no skips/failures, warnings as errors. Ruff, Python/Just formatting and warning-failing ty passed. Native tests include real Docker targets, scripted production ADK factories, Temporal workflows/replay/restart/cancellation, built-wheel loading, real CLI animation and three Ctrl+C detachment attempts. Package build and direct original/fixed reference commands succeeded with actual pytest/coverage and confirmed cleanup.

Local test correction: `tests/integration/test_cli.py` stops the PTY reader when `os.read` returns empty bytes. The old Linux-only OSError expectation produced an unbounded reader on Mac; no assertion was removed. Runtime src is unchanged. Setup docs now specify shared `TMPDIR` plus pytest `--basetemp`; Colima does not normally share the default Mac temp tree. Initial mount/PTY attempts remain failed/incomplete records, not passes.

Canonical final command, using the task-owned server while it was running:

```bash
export UV_PROJECT_ENVIRONMENT="$PWD/.work/mac-e2e-20261025/venv"
export UV_CACHE_DIR="$PWD/.work/mac-e2e-20261025/uv-cache"
export TMPDIR="$PWD/.work/mac-e2e-20261025/shared-tmp"
export DOCKER_HOST="$(docker context inspect colima --format '{{.Endpoints.docker.Host}}')"
export CORSAIR_TEMPORAL_ADDRESS=127.0.0.1:17373
export CORSAIR_LIVE_CONFIG="$PWD/.work/mac-e2e-20261025/live-settings-no-reasoning.json"
export OPENAI_API_KEY=EMPTY # Non-secret required SDK field for the user-selected unauthenticated endpoint.
export PYTHONDONTWRITEBYTECODE=1
nix develop --no-update-lock-file --command just check
nix develop --no-update-lock-file --command just -- test-all -q -W error \
  --basetemp="$PWD/.work/mac-e2e-20261025/pytest-qualified"
```

Do not reuse a nonempty pytest basetemp that contains material you need; pytest owns/clears that directory. The final suite's private JUnit receipt is `.work/mac-e2e-20261025/qualified-suite.xml`; reports and endpoint settings are under `outputs/mac-e2e-20261025`.

## Live-model boundary

User-selected endpoint advertises Qwen3.6-35B-A3B-NVFP4. Default thinking exhausted the frozen 512-token auditor smoke; existing native `reasoning_effort=none` passed that unchanged smoke. Repeated auditor freeze **6/6**, six actual calls. Producer freeze **0/3**, nine calls and nine tool calls: nested `plan` arrives as a JSON string, correctly rejected by canonical validation. Native SDK emits a valid PlanRevision reference; available evidence does not uniquely attribute the interoperability failure to model vs serving parser. A native annotation probe did not change SDK output and was reverted. No decoder, relaxation, larger frozen budget or model fallback was introduced. Full Qwen-driven live composition remains unrun/blocked by ISSUE-0009, despite the 120-test regression pass.

## Cleanup and continuation

Task-owned Temporal PID 63892 was verified through its exact `.work/mac-e2e-20261025/temporal.db` open-file identity, stopped with SIGTERM, and loopback 17373 closed. No labeled security containers remained. All five pre-existing user containers, Colima and older Temporal services are untouched. Private evidence and observer image remain retained. Tool service bookkeeping reported its shell stopped while the actual child listener was still live; actual port/database identity, not the job card, governed cleanup.

No commit/push/merge was performed. Local test/docs/record changes remain for review. Next: preserve them, investigate native typed nested-tool support under ISSUE-0009, re-run the unchanged producer freeze against its 0/3 baseline, and compose live Docker/Temporal only after that gate is qualified. Keep all raw endpoint/model/target diagnostics out of Git.
