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
- [ ] Framework row `jest` with the image row; a real Jest case (CVE-2020-7730 or CVE-2020-15123) at both commits.
- [ ] Mocha and AVA runners; environment `jest` admission with its own eval.

## Validation and progress

2026-10-13, cloud container, image-only (`node8` built locally from the same base digest via `mirror.gcr.io`, see PLAN-0062): marker files showed no test body or `beforeAll` ran in the listing; listing exit 0 with every test `pending`; execution exit 1 with the matcher failure at the test line and the `TypeError` case typed; syntax error exit 1 with no assertion results; a file outside `testMatch` exit 1 with no results. The gate's `node_offline` plus `node_runner_commands` via `docker exec` in that image passed (listing both fixture ids, both passed). Unit tests: 63 passed (`tests/unit/test_jest_runner.py`, `tests/unit/test_jest_report.py`).

## Decisions and next action

One file, identifier titles, never-matching-pattern listing (SPEC-0057). Next: the live gate, then the framework row.
