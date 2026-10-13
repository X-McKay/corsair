---
id: PLAN-0069
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
- [x] Image-only real case: CVE-2020-15123 (codecov-node) the same way.
- [ ] Framework row `jest` with the image row.
- [x] Harness guards as #74: an image config id, the checkout's HEAD blobs (`commit_tree`) rather than worktree bytes, and a fresh dependency directory per setup.
- [ ] Mocha and AVA runners; environment `jest` admission with its own eval.

## Validation and progress

2026-10-13, cloud container, image-only (`node8` built locally from the same base digest via `mirror.gcr.io`, see PLAN-0062): marker files showed no test body or `beforeAll` ran in the listing; listing exit 0 with every test `pending`; execution exit 1 with the matcher failure at the test line and the `TypeError` case typed; syntax error exit 1 with no assertion results; a file outside `testMatch` exit 1 with no results. The gate's `node_offline` plus `node_runner_commands` via `docker exec` in that image passed (listing both fixture ids, both passed). Unit tests: 63 passed (`tests/unit/test_jest_runner.py`, `tests/unit/test_jest_report.py`).

Real case, image-only, same local image: CVE-2020-7730 (nfriedly/node-bestzip) with the Corsair-written `benchmarks/cases/bestzip-command-injection/corsair.spec.js` as the patch. `setup` (`npm ci --ignore-scripts` from each commit's own lockfile, through the container proxy) exit 0 at both commits; the case's own Jest is 24.8.0. `run` offline (`--network=none`, capabilities dropped), one container per commit: baseline `fcea252e` discovered both ids, control passed, security failed (`Error` at `test/corsair.spec.js:23`, function `corsair_security`), 10.7 s; fix `45d4a901` discovered both, both passed, 10.6 s; container cleanup confirmed both times. Evidence stayed in the cloud container (not retained); the RIG0 batch repeats it with evidence under the worktree's `.runs`.

Second real case, image-only, same image (config id `sha256:744310a4…`): CVE-2020-15123 (codecov/codecov-node) with `benchmarks/cases/codecov-gcov-command-injection/corsair.test.js`. `setup` exit 0 at both commits; the case's own Jest is 24.9.0. Baseline `5f6cc62d` discovered both ids, control passed, security failed (`Error` at `test/corsair.test.js:27`, function `corsair_security`: the injected `touch` ran), 10.6 s; fix `c0711c65` both passed, 10.5 s; container cleanup confirmed both times. A first test version omitted `gcov-exec`/`gcov-args`; `sanitizeVar` threw on the missing option before the gcov command was built, so the baseline security test passed without reaching the sink. The control now asserts the gcov command was built (`debug` names the root). Evidence not retained, as above.


After #74's guards were adopted (image config id, committed tree, fresh dependency directory), the codecov case was rerun the same way in fresh directories: baseline control passed and security failed, fix both passed, cleanup confirmed.

## Decisions and next action

One file, identifier titles, never-matching-pattern listing (SPEC-0057). Next: the live gate, then the framework row.
