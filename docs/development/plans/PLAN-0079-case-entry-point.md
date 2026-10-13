---
id: PLAN-0079
kind: plan
title: Benchmark case entry point, cohort eval and runner from the selected framework
status: in_progress
updated: 2026-10-13
related: [SPEC-0060, SPEC-0068, SPEC-0057, PLAN-0070, IDEA-0005]
---

# Benchmark case entry point, cohort eval and runner from the selected framework

## Objective and dependencies

Turn a benchmark case id into chain input and run it, for any language whose framework has a case harness, without
changing `run_chain`'s stage order or the runtime selector (SPEC-0060, SPEC-0068). Kick-off shape agreed in the
project on 2026-10-13: `make eval AGENT=chain SET=<cohort>` for cohorts on the existing eval wrapper (indexed,
compared, promotable), `make run CASE=<id>` for one case (diagnosis, never a baseline), each case once with a fresh
run directory and no retries, a case that cannot start recorded before any model request, one result line per case
and a per-language roll-up of the stages reached. Al kept the approach (no tree-sitter, esprima stays).

## Steps

- [x] JavaScript assertion lines in authoring (`agents/test_authoring/javascript.py`, esprima 4.0.1, dev group);
  `static.py` dispatches by test id grammar through a `LANGUAGES` table and keeps Python's `ast` reader.
- [x] `framework_row(selection, matrix)`: the one framework row the selection admitted on its image; refuses zero or
  several.
- [x] `evals/case_e2e/frameworks.py`: harness table keyed by framework name (Jest first) with runner, runner config,
  dependency setup, workspace, scratch, observation facilities and witness recorders (none outside Python, so such
  cases stop at planning). A framework with no row is refused before any model request.
- [x] `evals/case_e2e/case.py`: manifest by case id or directory plus a local clone, each commit's own blobs,
  runtime inputs from the baseline's build files, setup source and issue source from manifest `setup_paths` and
  `source_paths` (new optional `AgentPart` fields), `revision_sources` = SHA-256 of the commit the Docker workspace
  copies.
- [x] `evals/case_e2e/docker.py`: environment stage sandbox (selected image, baseline tree, registry access during
  setup only) and offline runners, a fresh container per runner with the revision's own dependencies installed once
  per commit (`DockerCase` gains a `network` option, `commit_tree` any commit).
- [x] `record_run` takes the case's stages, scripted models, runtime catalog and preparation; fixture defaults kept.
- [x] `evals/case_e2e/run.py` (`make run CASE=`), `evaluate.py` (`make eval AGENT=chain SET=jest`),
  `results.py` (result line incl. reserved `baseline_basis`, roll-up), `cohorts.yaml`.
- [x] Manifests for CVE-2020-15123 (codecov-node) and CVE-2020-7730 (bestzip); issue text not yet owner-reviewed.
- [ ] Baseline test in the planner's saved inventory (finding below); chain thread's call.
- [ ] Ruby (Minitest) and Maven (JUnit) harness rows from their threads; pytest row.
- [ ] First live cohort when the model is free and Al says go.

## Validation and progress

2026-10-13, cloud container, main fa1b19c plus this branch. `make test-config`: 1774 passed (at 68d4ee1, before the
kick-off changes); `tests/agents/test_case_e2e.py` 9 passed, `tests/configuration/test_benchmark_cases.py` and
`tests/agents/test_javascript_assertions.py` passed.

No-model Docker check of the case command on CVE-2020-15123 with the local node8 image (config id
`sha256:744310a4…`), scripted stages, real Docker ports: both commits' dependencies installed (`npm ci
--ignore-scripts`), runtime selected `node-8.17.0-npm` with `jest` (image-only), the environment stage's sandbox ran
`npm ci` (exit 0, 645 packages), a build check, `jest --listTests` and `test/services/travis.test.js` through
`--json --runTestsByPath`; the ready environment was admitted (framework `jest`, cleanup confirmed). A first attempt
picked `test/git.test.js` as baseline, which exits 1 outside a git checkout; the agent was refused ready, as it
should be. Scripted identification then targeted `upload` in `lib/codecov.js`.

Finding: the run stopped at planning input, "the baseline test file must be in the saved inventory". The
environment stage chooses the baseline test at run time, but the planner's source inventory is the case's fixed
issue source, so every real case whose baseline test is not listed in `source_paths` stops there. Fixing it means
the chain adding the admitted baseline test file to the planner's source after the environment stage, which is
`run_chain`'s routing; raised with the coordinator rather than changed here. Evidence stayed in the cloud
container.

## Decisions and next action

Esprima for JavaScript assertion lines, as agreed before the brainstorm (Al kept the approach). The runner is picked
from the runtime selection before the chain; the environment stage can only confirm that framework, since its own
admission and `check_ready` refuse any other. Next: the chain thread decides how the admitted baseline test reaches
the planner's inventory; then the Ruby and Maven harness rows, and a live `jest` cohort on Al's go.
