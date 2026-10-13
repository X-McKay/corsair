---
id: PLAN-0064
kind: plan
title: Jest test runner and report parser
status: in_progress
updated: 2026-10-13
related: [SPEC-0057, SPEC-0055, PLAN-0062]
---

# Jest test runner and report parser

## Objective and dependencies

Implement [SPEC-0057](../specs/SPEC-0057-jest-runner.md) on top of the Node 8 image (SPEC-0055, PR #67), whose fixture and gate it extends. Live checks need the kind cluster after the Perl 5.26 thread.

## Steps

- [x] Check on Node 8.17.0 / Jest 24.8.0 that `--testNamePattern '(?!)'` lists tests without running bodies or hooks, and capture real reports.
- [x] `JsTestId`, `reports/jest.py`, `adapters/jest_runner.py`, unit tests over the captured reports; gate `node_runner_commands` on the fixture.
- [ ] Live: the node8 gate with the runner commands on RIG0.
- [x] Image-only real case: CVE-2020-7730 (bestzip) through `tests/qualification/node_image_case.py` at both commits.
- [ ] Framework row `jest` with the image row; CVE-2020-15123 (codecov-node) the same way.
- [ ] Mocha and AVA runners; environment `jest` admission with its own eval.

## Validation and progress

2026-10-13, cloud container, image-only (`node8` built locally from the same base digest via `mirror.gcr.io`, see PLAN-0062): marker files showed no test body or `beforeAll` ran in the listing; listing exit 0 with every test `pending`; execution exit 1 with the matcher failure at the test line and the `TypeError` case typed; syntax error exit 1 with no assertion results; a file outside `testMatch` exit 1 with no results. The gate's `node_offline` plus `node_runner_commands` via `docker exec` in that image passed (listing both fixture ids, both passed). Unit tests: 63 passed (`tests/unit/test_jest_runner.py`, `tests/unit/test_jest_report.py`).

Real case, image-only, same local image: CVE-2020-7730 (nfriedly/node-bestzip) with the Corsair-written `benchmarks/cases/bestzip-command-injection/corsair.spec.js` as the patch. `setup` (`npm ci --ignore-scripts` from each commit's own lockfile, through the container proxy) exit 0 at both commits; the case's own Jest is 24.8.0. `run` offline (`--network=none`, capabilities dropped), one container per commit: baseline `fcea252e` discovered both ids, control passed, security failed (`Error` at `test/corsair.spec.js:23`, function `corsair_security`), 10.7 s; fix `45d4a901` discovered both, both passed, 10.6 s; container cleanup confirmed both times. Evidence stayed in the cloud container (not retained); the RIG0 batch repeats it with evidence under the worktree's `.runs`.

## Decisions and next action

One file, identifier titles, never-matching-pattern listing (SPEC-0057). Next: the live gate, then the framework row.
