---
id: PLAN-0079
kind: plan
title: Issue entry point, benchmark cases and cohorts on it, runner from the selected framework
status: in_progress
updated: 2026-10-13
related: [SPEC-0060, SPEC-0068, SPEC-0057, SPEC-0037, SPEC-0038, SPEC-0040, PLAN-0070, IDEA-0005]
---

# Issue entry point, benchmark cases and cohorts on it, runner from the selected framework

## Objective and dependencies

A user supplies an issue as JSON (later also an issue id) and the system runs it end to end; benchmark cases and
cohorts call the same entry. `run_chain`'s stage order and the runtime selector stay as they are (SPEC-0060,
SPEC-0068). Kick-off shape agreed in the project on 2026-10-13 (Al: "a user can provide either an issue ID or a
json-representation of the issue"; "designed in a general way to work across languages, and we don't have to bake
any information or logic into specific images"): `uv run corsair run --issue-json <file>` is the product command (Al's naming);
`make run CASE=<id>` (diagnosis, never a baseline) and `make eval AGENT=chain SET=<cohort>` (indexed, compared,
promotable) both go through it; each case once with a fresh run directory and no retries; a request that cannot start
is recorded at admission before any model request; one record and summary line per issue, a per-language roll-up of
stages reached per cohort. Esprima stays for JavaScript assertion lines (Al kept the approach).

## Steps

- [x] JavaScript assertion lines in authoring (`agents/test_authoring/javascript.py`, esprima 4.0.1, dev group);
  `static.py` dispatches by test id grammar through a `LANGUAGES` table and keeps Python's `ast` reader.
- [x] `framework_row(selection, matrix)`: the one framework row the selection admitted on its image; refuses zero or
  several.
- [x] `corsair.investigation.request`: `corsair-issue-request/v1` with a captured ticket (`TicketSnapshot`) or a
  `manual` issue (title, body), repository (https, or `file://` under an operator-allowed root; a GitHub issue
  defaults to its own repository), exact vulnerable and fixed commits, optional scope and untrusted PoV. Runtime,
  framework, runner, witness target, budgets, policy, images, labels and oracles are not fields; extra fields are
  refused.
- [x] `corsair.investigation.frameworks`: the one table keyed by framework row name. An entry gives runner and its
  image-only config, one generic setup argv run with registry access (`npm ci --ignore-scripts` for Jest; for pytest
  `pip install --target .corsair-deps -r requirements.txt` constrained to the image's own packages), the
  dependency directory and the lockfiles binding it, scratch and observation facilities, witness recorders (none
  outside Python, so such issues stop at planning). Code never branches on a language; `Toolchain.language` is a
  pattern-checked string, not a fixed list.
- [x] `corsair.investigation.build`: acquisition at the exact commits (`file://` roots, or SPEC-0037
  `GitAcquisition` on allowed hosts), each commit's own blobs, runtime inputs from the baseline's build files, setup
  source = build and CI files within the environment stage's bounds, issue source = files the issue names (refused
  when none: repository-scale identification, SPEC-0038, is not in the chain), `revision_sources` = SHA-256 of the
  commit the Docker workspace copies.
- [x] `corsair.investigation.docker`: generic dependency install (one container per commit from the table's setup,
  receipt bound to commit, image and lockfile digests), the environment stage's sandbox on the selected image, and
  offline runners with a fresh container each. `corsair.adapters.docker_image` holds the shared Docker helpers;
  `corsair.composition.receipts` the receipts (moved from `evals/fixture_e2e/run.py`, re-exported there).
- [x] `corsair` console script (`[project.scripts]`, uv_build backend, `src/corsair` a namespace package), `corsair run` in `corsair.investigate`, `make investigate ISSUE_JSON=` a wrapper: request, record and summary line, receipts under a new
  private evidence directory; `corsair.investigation.results` record incl. reserved `baseline_basis`
  ("project" | "operator_smoke"), cohort roll-up.
- [x] Headline label first in the record and summary line (`results.headline`, one table; Al, 2026-10-13):
  LIKELY_EXPLOITABLE (gate completed, finding reproduced); LIKELY_NOT_EXPLOITABLE (completed, not_reproduced or
  refuted_in_scope); INCONCLUSIVE (completed and inconclusive, a model stage's own outcome ended the run, or a
  model stage ran without answering: its token, request or tool-call budget ran out, or its answer never validated
  on any output retry, the last refusal recorded as `last_refusal`); UNABLE_TO_RUN (stopped at admission, runtime or
  environment for a case reason, or execution blocked/unsupported); ERROR (execution failed or unknown, a provider,
  timeout or harness failure, a stage's own time limit, or a crash). The stage and reason follow; the eval match still compares the three-part result; the cohort counts per label.
- [x] `evals/case_e2e`: a case becomes its issue request (manual issue, `file://` clone under
  `CORSAIR_CASE_SOURCES`) plus `expected.json` the entry never reads; `run.py` (`make run CASE=`), `evaluate.py`
  (`make eval AGENT=chain SET=jest`), `cohorts.yaml`.
- [x] Manifests for CVE-2020-15123 (codecov-node) and CVE-2020-7730 (bestzip); issue text names the vulnerable file,
  not yet owner-reviewed.
- [x] pytest image-only entry (runner on `/usr/local/bin/python3`, the `audit_open` witness recorder) and SPEC-0071
  smoke overlays: the Docker preparation writes the overlay beside the commit (refusing a path the commit has) and
  every runner workspace gets the same overlay.
- [ ] Witness envelope: `build` sets none, so the chain requests no witness on this route (an operator-approved
  envelope is fixture-only today).
- [ ] Baseline test in the planner's saved inventory (finding below); chain thread's call.
- [x] `--id github:owner/repo#N | azure:org/project#N` (make `ID=`) through the existing ticket readers; a GitHub
  issue defaults to its own repository, Azure DevOps needs the configured source and `--repository`.
- [ ] Ref resolution (branch or default branch to a commit) and vulnerable-only runs (no fixed commit).
- [ ] Ruby (Minitest), Maven (JUnit) and pytest image-only entries from their threads; operator smoke test.
- [ ] First live cohort when the model is free and Al says go.

## Validation and progress

2026-10-13, cloud container, main fa1b19c plus this branch. `tests/agents/test_case_e2e.py` 11 passed (request
schema, build from a throwaway clone, admission refusals, framework table, language not a list, the two cases as
request plus expectation, environment stage in the run record, framework mismatch, records and roll-up, a cohort
case refused before any model); `make test-config` 1779 passed. The environment agent's offered toolset digest
changed (`list_toolchains` now offers `language` as a pattern-checked string, not seven fixed values), repinned to
`75f1363f…`; scripted `make eval AGENT=environment` 16/16 clean. Its live baseline needs a rerun on the new digest.

No-model Docker check through `run_case` and `investigate` on CVE-2020-15123 with the local node8 image (config id
`sha256:744310a4…`), scripted stages, real Docker ports: both commits' dependencies installed by the table's setup,
runtime selected `node-8.17.0-npm` with `jest` (image-only), the environment stage's sandbox ran `npm ci`, a build
check, `jest --listTests` and `test/services/travis.test.js` through `--json --runTestsByPath`; the ready
environment was admitted (framework `jest`, `baseline_basis` "project", cleanup confirmed). An earlier attempt picked
`test/git.test.js` as baseline, which exits 1 outside a git checkout; the agent was refused ready, as it should be.

Finding: the run stopped at planning input, "the baseline test file must be in the saved inventory". The
environment stage chooses the baseline test at run time, but the planner's source inventory is the fixed issue
source, so every real issue whose baseline test file the issue does not name stops there. Fixing it means the chain
adding the admitted baseline test file to the planner's source after the environment stage, which is `run_chain`'s
routing; with the chain thread. Evidence stayed in the cloud container.

Pytest route, 2026-10-13, cloud container with a local CPython 3.12 image built from the pinned wheels: on the
first corpus case (ih-python-pathtraversal, corpus bundle merged on a scratch branch) the scripted run installed
both commits' requirements, admitted the environment on the operator smoke test (`baseline_basis` operator_smoke,
cleanup confirmed) and reached planning with the smoke file in the planner's inventory. The Docker runners on both
revisions with a hand-written control and security pair and a witness request: baseline control passed, security
failed, candidate both passed, witness captured on both.

## Decisions and next action

Esprima for JavaScript assertion lines. The runner is picked from the runtime selection before the chain; the
environment stage can only confirm that framework, since its own admission and `check_ready` refuse any other.
Images stay plain pinned upstream runtimes; per-framework facts live in the one table. Next: the chain thread decides
how the admitted baseline test reaches the planner's inventory; then the issue-id path and the other frameworks'
image-only entries, and a live `jest` cohort on Al's go.
