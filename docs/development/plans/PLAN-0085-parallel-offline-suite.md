---
id: PLAN-0085
kind: plan
title: Parallel offline suite in CI
status: complete
updated: 2026-10-13
related: [PLAN-0002]
---

# Parallel offline suite in CI

## Objective and dependencies

PR CI (`Development guards`) is one job that runs `make test-config`, the whole offline suite, serially. On 23 PR runs on
2026-10-13 the median wall-clock was 3 min 32 s (range 2:33 to 4:47) against a 5-minute job timeout; queue, checkout and uv
setup together took under 10 s, so pytest was about 96% of each run. The suite is CPU-bound (locally `user` time is close to
`real`), and the runner has 4 vCPUs (public repository). Timing table and per-file breakdown: project file
`handoffs/ci-duration-2026-10-13.md`. No dependency on other work; CI still never calls the model, toolchain images stay
image-only, and the record-id and development-workflow checks keep running on every PR.

## Steps

- [x] Pin `pytest-xdist==3.8.0` in the dev dependency group (uv.lock adds it and `execnet==2.1.2`).
- [x] `make test-config` runs with `-n $(TEST_WORKERS)`, default `auto`; `TEST_WORKERS=0` in the environment runs serially.
- [x] Raise the `offline-guards` job timeout from 5 to 10 minutes so suite growth or a slow runner is not a false red.
- [x] Compare the first CI run on this branch against the 2026-10-13 serial baseline.

## Validation and progress

Local container, 4 cores, branch on main 9ad65fb:

- `TEST_WORKERS=0 make test-config`: 1966 passed in 324 s (real 5:28).
- `make test-config` (4 workers): 1966 passed in 117 s (real 1:58).
- `make test-config TEST_WORKERS=0` (command-line form) fails `test_pre_allowed_targets_keep_values_out_of_recipe_text`:
  the variable reaches the guarded `qualify-image` sub-make through MAKEFLAGS and is refused. Not a suite failure; the
  Makefile comment names the environment form.
- Under xdist, `tests/unit/test_sandbox_execution.py` emits `DeprecationWarning: This process ... is multi-threaded, use of
  fork() may lead to deadlocks in the child` (from `multiprocessing` in the worker). It passed in every parallel run; if it
  ever hangs, `--dist loadfile` or a serial mark for that file is the first step.

CI on e8aae0c (PR #124, job 115519469174): `offline-guards` 2:21 wall (20:20:40 to 20:23:01Z), 1966 passed in 129 s
on 4 workers, against a median of 3:32 wall and ~200-250 s of pytest on 23 serial PR runs the same day. The same 10
fork warnings from `test_sandbox_execution.py`; no hang.

## Decisions and next action

xdist is the standard pytest plugin for this; no bespoke sharding or workflow matrix. Not changed: the slow-file costs
themselves (`test_toolchain_selection.py` spawns a `pytest --collect-only` per case, ~30 s serial), left for a separate small
change. Next: none in this plan; merge on Al's word.

Superseded in part by PR #135 (2026-10-14, Al deferred gates and CI until something runs end to end): a workflow
matrix now exists. `--test-shard k/n` (tests/conftest.py, `TEST_SHARD=k/n make test-config`) takes every n-th
collected test; the v1 suite runs as three shards from `offline-v1.yml` on manual dispatch and main pushes, off the PR
path, whose `offline-guards` check runs only `make test-v2`; xdist uses `--dist worksteal`. Locally (4 cores, develop
58c2d9b) shards 779/779/778 passed in 35/37/39 s, unsharded 2336 in 82 s (106 s with the default distribution). CI on
ec47122 (three shards + v2 job): green, 2:03 wall, shards 47/75/119 s.
