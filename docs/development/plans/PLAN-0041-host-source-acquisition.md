---
id: PLAN-0041
kind: plan
title: Host acquisition of exact benchmark commits
status: in_progress
updated: 2026-10-13
related: [SPEC-0037, SPEC-0012, SPEC-0025, PLAN-0021]
---

# Host acquisition of exact benchmark commits

## Objective and dependencies

Implement [SPEC-0037](../specs/SPEC-0037-host-source-acquisition.md): a host step that fetches each benchmark case's fix commit at its exact SHA, verifies and measures it, and hands a typed `FetchTarget` on to the SPEC-0025 sandbox fetch. This is IDEA-0005 step 2 (gap G2c), proposed in the benchmark readiness inventory on the separate `claude/benchmark-readiness-7xbmvr` branch. No dependency on the kind cluster, the local model or that branch; the sandbox fetch itself stays blocked on the workspace storage quota.

## Steps

- [x] Adapter `src/corsair/adapters/git_acquire.py` (`GitAcquisition`, `HostTransport`, `AcquireLimits`, `TreeStats`, `AcquiredSource`) with offline tests `tests/unit/test_git_acquire.py`.
- [x] Case resolver and runner `evals/benchmark/sources.py`; resolver and pins consistency checks `tests/configuration/test_benchmark_sources.py`.
- [x] Smoke: two cases (JSPWiki, dot-prop) end to end, including `GitSource` capture of fix and parent.
- [ ] Network run of all resolved cases; commit `benchmarks/source-pins.json`.
- [ ] Review, CURRENT.md row, handoff, draft PR.

## Validation and progress

Offline: `uv run --locked python -m pytest tests/unit/test_git_acquire.py` 10 passed. The first draft failed three of its own tests, each a real finding fixed in the adapter or test: `git init` copied sample hooks larger than a small file-size limit (now `--template=`), a file-size kill surfaces as `index-pack died of signal 25` with fetch exit 128 rather than a signal exit (now classified `budget`), and a test fixture's `\0100` octal escape.

Smoke (2026-10-13, cloud container through its egress proxy, `.runs/acquire-smoke/`): JSPWiki fix `88d89d65` acquired with complete ancestry in 7.4 s, 54,258,721 repository bytes, 1,724 files / 14,132,441 bytes; single parent `f140a2a4`, matching the hand acquisition recorded in PLAN-0021 (54,258,800 bytes then, which included template hooks); `GitSource` captured both at the largest admitted ceilings (1,724 and 1,723 files). dot-prop 89,558 bytes, 15 files.

A first full run was stopped after two cases to rerun on the final adapter (template-free init); its partial output is kept as `.runs/acquire-20261013-superseded/`.

## Decisions and next action

Complete ancestry by default, not shallow, because the qualified `GitSource` capture refuses shallow repositories; `--depth` stays available as an explicit measure-only mode. Fetch from the repository named in the fix reference and flag disagreement with the inventory's `repository_url`, rather than guessing. The runner deletes fetched repositories and captured objects after recording unless `--keep`; receipts stay.
