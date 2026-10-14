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
- [ ] RIG0: fresh cluster in this branch's worktree per [the runbook](../../runbooks/openshell-v2.md); `make qualify-openshell-v2` green; Docker passes the same port suite on RIG0.
- [ ] RIG0: one decisive case on OpenShell and on Docker with the same verdict, reason and per-probe outcomes; cleanup confirmed.
- [ ] Fix whatever the live run shows (the open facts in HANDOFF-0136), then mark the backend qualified and record evidence paths.

## Validation and progress

2026-10-14 (cloud container, no Docker, kind or gateway): `uv run --locked python -m pytest -c pyproject.toml --rootdir=. -n auto tests` -> 1575 passed, 117 skipped (every Docker and live OpenShell test skipped). Recording fake docker CLI: old and new code gave identical outputs and identical docker argv for replay x2, run_probe, diagnose and sweep. Nothing ran live.

## Decisions and next action

Tar over exec stdin instead of CLI upload: the SDK keeps the data path, and symlink handling is ours. Environments on OpenShell replay a sealed recipe per probe (SPEC-0083). Next: the RIG0 steps above, when the coordinator hands this branch the cluster.
