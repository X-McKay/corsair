---
id: HANDOFF-0141
kind: handoff
title: Just and Nix for Linux amd64 and macOS arm64
status: complete
updated: 2026-10-25
related: [PLAN-0108, HANDOFF-0140]
---

> Historical record. Commands, counts and status describe the recorded revision, not the current working tree. See [current work](../../README.md) for current guidance.

# Just and Nix for Linux amd64 and macOS arm64

One branch/PR contains the entire requested migration. Makefile is removed; all active commands use the documented justfile. Positional task arguments use quoted `$@`, including paths with spaces or shell characters. `just` alone lists tasks and does not start work. Ruff, Just formatting and warning-failing ty remain the required `just check` gate.

`flake.nix` has one Nixpkgs input, pinned by the generated flake.lock at `3ec636362e1816bc2f0888fa0fa2c69f1bc9e504`. Only `x86_64-linux` and `aarch64-darwin` shells are exposed. Native Python 3.12.15, uv, Just, Bash, Docker client and Temporal CLI are selected by that pin; UV_PYTHON points to the exact Nix interpreter and managed downloads are disabled. Python dependencies remain in the unchanged uv.lock. CI rejects lock updates and enters this same shell.

Source admission is now capability-based rather than Linux-name based, with no path fallback. Added real-host and missing-capability regressions; existing symlink/replacement/archive/oracle checks remain. The observer, its Docker image definition, SDK versions, prompts, fixtures/datasets, verdict policy and cancellation ownership are unchanged.

## Local final results

```bash
just check
DOCKER_HOST=unix:///run/user/1000/docker.sock \
CORSAIR_LIVE_CONFIG=.state/live.json just -- test-all -q -W error
just -- eval-agent auditor evals/datasets/auditor-dev.json \
  --settings .state/live.json --repeats 3 \
  --output .runs/evaluations/just-final-auditor.json
just build
```

Final post-cleanup suite: **116 passed in 110.27 seconds**, no skips, warnings as errors; actual Docker, Temporal, CLI, installed-wheel and live-auditor gates enabled. First migration run was 110 passed in 111.95 seconds; the final run includes the added capability tests. Final frozen auditor: **6/6 passed**, six model calls, no operational failures, 12 JSONL lifecycle events. Just separately echoes its safe recipe command to stderr; command-result stdout remains JSON. Raw outputs/configuration remain ignored.

Both target flakes evaluated successfully with `nix flake check --all-systems --no-build --no-update-lock-file`. Local host is Linux ARM, outside the supported matrix; local results are regression evidence, not target qualification. Actual target checks are in common CI: Linux amd64 native Docker/Temporal gates and macOS-26 ARM full offline/Temporal gates. The PR/packaged CI receipt records their final result.

Nix/tool/dependency selection is reproducible, not a fully hermetic/offline image build. A direct local rebuild in the portability worktree failed in the unchanged external pip installation layer; no provider/runtime change was substituted. Final native regression tests used the already qualified unchanged observer image. Target CI performs the real image build again.

## Limits and follow-ups

macOS needs Docker Desktop or Colima's Linux daemon for targets. Hosted ARM runners lack nested virtualization, so physical-Mac full Docker-chain qualification is not claimed. Docker SDK context/socket setup and shared paths are documented in [platform support](../../../reference/platforms.md). Live security-producer policy blocking, population accuracy and arbitrary hostile-interpreter attestation remain unqualified.

Use [environment setup](../../../development/setup.md) for the golden path and [next simplifications](../reviews/2026-10-25-next-simplifications-base-review.md) for identified—but not silently implemented—report provenance, names-only listing, duplicate source read and early input-validation improvements. Historical handoffs preserve the original Make commands as dated evidence.

## Target CI interruption fix

Initial Nix-native CI reproduced intermittent client process hangs after `cli.interrupted` was already logged. Failure-only faulthandler captured interpreter garbage collection, not a blocked or ignored SIGINT. The CLI raised SystemExit inside the active exception handler, retaining the cancelled stack's SDK objects through exception context. It now assigns the exit code in each handler and raises SystemExit after the handler has ended. This releases handled tracebacks before interpreter shutdown, preserves exit codes/logging, and uses no forced exit or private SDK cleanup hook. A real-command context regression and three repeated native detachment attempts cover the change.

The exception-context cleanup was useful but did not alone eliminate repeated Nix-native teardown failures. Client-only connection now lives in runtime/client.py, without importing worker/ADK composition. CLI completion observes bounded native SDK describe calls and retrieves the SDK result after closure, rather than cancelling an active history long-poll at process exit. It has no forced exit, private shutdown hook, GC disabling or remote cancellation. Installed-wheel/import-boundary tests and repeated real detachment tests cover this narrower lifecycle ownership. The latest delivered receipt distinguishes final results from the initial 116-test migration baseline.

## Final qualified result

The final client-only code revision passed **120 tests in 139.91 seconds**, all local native/live gates enabled with warnings as errors, and the final frozen auditor passed **6/6** again. Both push and PR CI passed every job on the same code: Linux amd64 offline/package, native Docker/Temporal integration, durable workflows/replay, and macOS arm64 offline/package/Temporal with repeated Ctrl+C detachment. Validated code revision: `715886238b3757970d35b0b7de3832e8b231fc06`; [successful target CI](https://github.com/X-McKay/corsair/actions/runs/40203541340). This supersedes the initial 116-test baseline above. Final documentation-only receipt updates do not change Python, tests, Just, Nix or SDK lock content.
