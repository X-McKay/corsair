---
id: PLAN-0070
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
- [ ] Live: the node8 gate with the runner commands, in the milestone gate batch (SPEC-0062 lighter path); it upgrades both rows to `live`.
- [x] Image-only real case: CVE-2020-7730 (bestzip) through `tests/qualification/node_image_case.py` at both commits.
- [x] Image-only real case: CVE-2020-15123 (codecov-node) the same way.
- [x] Image row `node-8.17.0-npm` and framework row `jest` (`==24.8.0 || ==24.9.0`), both `evidence: image-only`.
- [x] Harness guards as #74: an image config id, the checkout's HEAD blobs (`commit_tree`) rather than worktree bytes, and a fresh dependency directory per setup; setup writes a receipt (commit, image, `package-lock.json` SHA-256, exit 0) beside `node_modules` and `run` refuses a directory whose receipt does not match its own commit, image and lockfile, recording the receipt in `run.json`.
- [ ] Mocha and AVA runners; environment `jest` admission with its own eval.

## Validation and progress

2026-10-13, cloud container, image-only (`node8` built locally from the same base digest via `mirror.gcr.io`, see PLAN-0062): marker files showed no test body or `beforeAll` ran in the listing; listing exit 0 with every test `pending`; execution exit 1 with the matcher failure at the test line and the `TypeError` case typed; syntax error exit 1 with no assertion results; a file outside `testMatch` exit 1 with no results. The gate's `node_offline` plus `node_runner_commands` via `docker exec` in that image passed (listing both fixture ids, both passed). Unit tests: 63 passed (`tests/unit/test_jest_runner.py`, `tests/unit/test_jest_report.py`).

Real case, image-only, same local image: CVE-2020-7730 (nfriedly/node-bestzip) with the Corsair-written `benchmarks/cases/bestzip-command-injection/corsair.spec.js` as the patch. `setup` (`npm ci --ignore-scripts` from each commit's own lockfile, through the container proxy) exit 0 at both commits; the case's own Jest is 24.8.0. `run` offline (`--network=none`, capabilities dropped), one container per commit: baseline `fcea252e` discovered both ids, control passed, security failed (`Error` at `test/corsair.spec.js:23`, function `corsair_security`), 10.7 s; fix `45d4a901` discovered both, both passed, 10.6 s; container cleanup confirmed both times. Evidence stayed in the cloud container (not retained); the RIG0 batch repeats it with evidence under the worktree's `.runs`.

Second real case, image-only, same image (config id `sha256:744310a4…`): CVE-2020-15123 (codecov/codecov-node) with `benchmarks/cases/codecov-gcov-command-injection/corsair.test.js`. `setup` exit 0 at both commits; the case's own Jest is 24.9.0. Baseline `5f6cc62d` discovered both ids, control passed, security failed (`Error` at `test/corsair.test.js:27`, function `corsair_security`: the injected `touch` ran), 10.6 s; fix `c0711c65` both passed, 10.5 s; container cleanup confirmed both times. A first test version omitted `gcov-exec`/`gcov-args`; `sanitizeVar` threw on the missing option before the gcov command was built, so the baseline security test passed without reaching the sink. The control now asserts the gcov command was built (`debug` names the root). Evidence not retained, as above.


After #74's guards were adopted (image config id, committed tree, fresh dependency directory), the codecov case was rerun the same way in fresh directories: baseline control passed and security failed, fix both passed, cleanup confirmed.

Row check, 2026-10-13, cloud container, on main 86b37ce plus #92 (the `evidence` field): both cases reran through `node_image_case.py` in fresh directories with the same image config id `sha256:744310a4…`. Installed Jest 24.8.0 (bestzip) and 24.9.0 (codecov-node). bestzip: baseline `fcea252e` control passed, security failed at `test/corsair.spec.js:23`; fix `45d4a901` both passed. codecov-node: baseline `5f6cc62d` control passed, security failed at `test/corsair.test.js:27`; fix `c0711c65` both passed. Container and workspace cleanup confirmed on all four runs. With the new rows, `select` routes all four commits' build files to `node-8.17.0-npm`. The rows list npm 6.13.4 only: Yarn 1.21.1 is in the image but no case has run with it. The environment agent does not admit `jest` yet, so JavaScript cases select the image but stop at environment admission until that follow-up lands.

## Decisions and next action

One file, identifier titles, never-matching-pattern listing (SPEC-0057). Next: Mocha and AVA as drivers after the consolidation PR; environment `jest` admission; the milestone gate upgrades the rows to `live`.

Review fixes at the same head: a non-string assertion `status` (for example `[]`) is refused as a malformed report instead of raising `TypeError`; the runner binary must be absolute. With the receipt, the codecov case was rerun in fresh directories (baseline control passed, security failed; fix both passed; cleanup confirmed), and running the fix commit against the baseline's dependency directory was refused before any container started.

Consolidation (Al, 2026-10-13: generalize across languages and frameworks; one refactor PR after the runners merge, not per-PR rework). Parts of this PR that move into shared code:

- Listing: `JestRunner._stages` (list, compare exactly to the two ids, then one execution) is the same shape as Maven's; only the listing argv and `reports/jest.py:listed` differ, so a framework driver supplies `listing_argv`, `parse_listing`, `execution_argv` and `parse_report`, and the stage order, exact-match check and exit-code consistency (`_run_once`) become shared.
- Report admission: `admit_json` (bounded UTF-8, no duplicate keys) sits beside `junit.admit_xml`; the per-id rules (exactly one result per expected id, anything else only skipped or pending, outcome and failure consistent) and the frame-to-patch-path location in `_failure` repeat `junit.py`/`surefire.py` and become one admission layer with per-format readers and per-language frame patterns.
- Image-case script: `node_image_case.py` already imports `docker`, `user`, `plain` and `commit_tree` from `java_image_case.py`; `DockerCase`, `run` and `main` differ only in the dependency mount (`/modules` vs the Maven repository), the setup command and the runner class, so one script takes those from a per-language table.
- Ids: `JsTestId` stays per language (grammar), behind one parse entry point keyed by framework.

