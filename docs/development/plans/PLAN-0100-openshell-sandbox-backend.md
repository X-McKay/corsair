---
id: PLAN-0100
kind: plan
title: OpenShell backend for v2, implementation and qualification
status: in-progress
updated: 2026-10-14
related: [SPEC-0083, SPEC-0082, PLAN-0097, HANDOFF-0136]
---

# OpenShell backend for v2, implementation and qualification

## Objective and dependencies

Implement [SPEC-0083](../specs/SPEC-0083-openshell-sandbox-backend.md) on develop, then qualify it on RIG0. The live steps need the single RIG0 kind cluster and the one live-inference slot, which the build owner holds during the PoV spread. The coordinator sequences the handover. Docker remains the default throughout.

## Steps

- [x] Sandbox port and explicit backend selection; Docker implements it with identical docker argv.
- [x] Replay, probe execution, the D3 check run, the reconciler and the Builder workspace run through the port.
- [x] OpenShell backend (SDK lifecycle, exec, tar transfer; CLI policy set with load confirmation; environment manifests), v2 policies.
- [x] kind/OpenShell setup restored from 9c3bc62; `openshell-images-load`, `openshell-config`, `qualify-openshell-v2`; runbook; dead link in the toolchain report fixed.
- [x] Shared `Sandboxes` port suite (Docker + live OpenShell), live `WorkspaceBackendSuite` for OpenShell, offline adapter tests.
- [x] RIG0: fresh cluster in this branch's worktree per [the runbook](../../runbooks/openshell-v2.md); `make qualify-openshell-v2` green; Docker passes the same port suite on RIG0.
- [ ] RIG0: one decisive case on OpenShell and on Docker with the same verdict, reason and per-probe outcomes; cleanup confirmed.
- [x] Fix whatever the live conformance run shows and record evidence paths (the backend's conformance is qualified; the decisive case on both backends is still open).

## Validation and progress

2026-10-14 (cloud container, no Docker, kind or gateway): `uv run --locked python -m pytest -c pyproject.toml --rootdir=. -n auto tests` -> 1575 passed, 117 skipped before review; after the review fixes 1588 passed, 117 skipped (every Docker and live OpenShell test skipped). Recording fake docker CLI: old and new code gave identical outputs and identical docker argv for replay x2, run_probe, diagnose and sweep; `tests/v2/test_docker_argv.py` now pins that recording. An independent review found no Docker behaviour change and nine OpenShell findings (baseline not rerun on open, base digest not pinned, unbounded copy memory, a gRPC channel per call, policy readback and GET-only checks, live cleanup evidence, a stale Docker test tag, runbook overstatement), all fixed. Nothing ran live.

2026-10-14 post-merge follow-up (after #169, branch `followup` from 06d4cbe; cloud container, nothing live): a live RIG0 run refused every create with `name exceeds maximum length (51 > 19)`, and review found that the toolchain images (uid 10001) have no `/work`. Changes: native sandbox names are at most 19 characters (`cv2-` plus 15 hex of the port name's sha256; valid short names kept; full name in the `corsair.v2.name` label). `Sandboxes.workdir` is new (Docker `/work`, OpenShell `/sandbox`); `build.replay` defaults to it, so Environments and execute follow, and the OpenShell agent workspace uses it. The v2 policies use `include_workdir` with `read_write: [/tmp, /dev/null]` and drop `/lib64`; `check_policy` requires `include_workdir`. `OpenShellWorkspace.run` maps DEADLINE_EXCEEDED to kill plus `WorkspaceTimeoutError`, other transport errors to `WorkspaceError`, and applies the 124 check to the default limit too. `resolve_image` resolves a sealed environment tag to its pinned base digest ref (RUN_RECORD.md updated). `seal_environment` takes replay's real timeouts. `find_environment` returns None when the sealed tree is gone or changed, so replay rebuilds. `workflow.container_timeout` adds setup plus baseline to diagnose and execute on OpenShell (Docker unchanged; `RunRequest.workspace`). `from_config` caches by path and mtime. The live drop-network test now uses the python image and requires a real GET to pypi.org under `build` before the drop, failing after it. `tests/v2/test_docker_argv.py` is unchanged and passes.

Codex review of #171 (b8c634a), both fixed: (1) on open, every replayed step now shares one `REPLAY_BUDGET_S` (3600s, the replay activity's own bound, which the sealed replay already completed within), so a 32-step recipe cannot outrun the diagnose/execute activity; `REPLAY_ON_OPEN` is that budget. (2) `_KILL` now exits 0 only when `kill -0` confirms the process gone, and a timeout says "termination is unconfirmed" otherwise instead of "was killed". Offline: 1637 passed, 117 skipped.

RIG0 conformance rerun on 9a5cd7b0 (2026-10-14, evidence `.runs/openshell-v2-20261014T125737Z/` in the RIG0 worktree, no model): `qualify-openshell-v2` 44 passed, 3 failed, 1 skipped (SupportsRealpath not implemented); Docker suites 52 passed, 11 skipped; cleanup.jsonl 51 lines, all confirmed; no sandboxes left. The name-length failure is gone. The three failures and their fixes: (1) `/sandbox` is root-owned but writable by uid 10001 under `include_workdir`, so the port contract and its test now require a writable workdir in which the command user owns what it creates, not ownership of the root itself. (2) The gateway refuses any argument over 32 KiB (`command argument 7 exceeds 32768 byte limit`), and PydanticAI's shell `write_bytes` sends 64 KiB chunks; a command with a longer argument is now staged through stdin as a self-removing script that execs exactly that argv (`ARG_LIMIT`, `_deliverable`, used by `exec_once` and `OpenShellWorkspace.run`); the fake enforces the cap. (3) `test_background_child_does_not_hold_up_completed_command` failed with a bare assertion (site-packages code is not rewritten); the test class now runs the same test with the result in the message, and a stream ending without an exit status is a `WorkspaceError`, not an `assert`. Cause of (3) not yet known; the next rerun shows it.

RIG0 rerun on bc952552 (evidence `.runs/openshell-v2-20261014T141652Z/`): 46 passed, 1 failed, 1 skipped; Docker 52 passed, 11 skipped; cleanup.jsonl 51 lines, all confirmed; no sandboxes left. The workdir and large-write fixes hold. The remaining failure shows its values: `CommandResult(exit_code=74, stdout='done', stderr='openshell: exec output could not be delivered intact')`. When a background child still holds the exec's pipes after the command exits, the gateway reports exit 74 instead of the command's status. Fix: `OpenShellWorkspace.run`'s wrapper runs the command with its output in files under `/tmp`, waits for it, and then replays stdout and stderr; it records both pids so `_KILL` kills the group, or the command and the wrapper, and confirms both gone. `exec_once` (trusted probes) maps exit 74 with that gateway text to `container_failed`, so it is never read as a program's exit code.

RIG0 rerun on 11fa46f0 (evidence `.runs/openshell-v2-20261014T145942Z/` in the RIG0 worktree; admission and network evidence for the same cluster in `.runs/openshell-v2-20261014T113137Z/`; no model): `qualify-openshell-v2` 47 passed, 0 failed, 1 skipped (`SupportsRealpath` is not implemented; Docker skips the same test). The shared port suite passed 10 of 10 on OpenShell; PydanticAI's `WorkspaceBackendSuite` 37 passed, 1 skipped. Docker suites 52 passed, 11 skipped. cleanup.jsonl 51 lines, all confirmed; `kubectl get sandboxes -A` empty afterwards. The OpenShell backend's conformance is qualified on RIG0. Still open: one decisive case on OpenShell and on Docker (needs a model slot). The cluster stays up, owned by that worktree.

## Decisions and next action

Tar over exec stdin instead of CLI upload: the SDK keeps the data path, and symlink handling is ours. Environments on OpenShell replay a sealed recipe per probe (SPEC-0083). Next: the RIG0 steps above, when the coordinator hands this branch the cluster.
