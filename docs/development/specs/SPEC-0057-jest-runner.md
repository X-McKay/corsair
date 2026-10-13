---
id: SPEC-0057
kind: spec
title: Jest test runner and report parser
status: draft
updated: 2026-10-13
related: [SPEC-0055, SPEC-0039, SPEC-0041, SPEC-0042, PLAN-0070]
---

# Jest test runner and report parser

## Goal and scope

The Node 8 image (SPEC-0055) runs no case without a Corsair runner for the case's test framework. Two of its five cases use Jest 24 (CVE-2020-15123, CVE-2020-7730). This spec adds the Jest runner under the existing runner contract (`adapters/native_runner.py`, as `maven_runner.py` in SPEC-0039/SPEC-0041): a test id grammar, discovery that lists without running tests, one execution, and claims from Jest's own JSON report. Not in scope: Mocha (GHSA-xxvw-45rp-3mj2, `@vivaxy/here-3.1.0`) and AVA (CVE-2020-8116), which follow under their own records; the environment agent's `jest` baseline admission in `agents/environment/frameworks.py` (it admits project tests whose titles need not be identifiers, so it needs its own id form and an environment eval); a Node witness probe; and authoring or planning JavaScript tests, which today are Python-only (`TEST_ID` in the authoring contract), the same gap the Java runner has.

## Boundaries and design

Ids are `path/file.test.js::[suite::]name` (`ports.test_runner.JsTestId`): one optional top-level `describe` and identifier segments, so Jest's full name (ancestor titles and title joined by a space) maps back to exactly one id and a name pattern needs no escaping. Both tests are in one file (one Jest test result to admit, as one class for Surefire). Titles that are not identifiers cannot be addressed; the authoring side writes Corsair's tests, so it can keep to the grammar.

`JestRunnerConfig.command` is the operator's prefix: a Node binary, the project's Jest CLI script and options only, none of which select or report tests (`-t`, `--testPathPattern`, `--json`, `--watch`, … are refused); the environment's discovery command is recorded, never executed. The report path is an absolute operator path outside the workspace. Both stages run one fixed `/bin/sh` wrapper with every value positional: Jest's console to stderr, stdout exactly the JSON file Jest wrote, exit status Jest's. Discovery is `--runTestsByPath <file> --testNamePattern '(?!)'`: a pattern no name matches, so Jest loads the file and reports every test `pending` by name, running no test body and no hook (module top-level code runs, as pytest collection imports). It must exit 0 and list exactly the two ids. Execution is `--runTestsByPath <file> --testNamePattern '^(?:<full name>|<full name>)$'`, once, never retried.

`reports/jest.py` admits the report: bounded UTF-8 JSON without duplicate keys, exactly one test result named `<root>/<file>`, assertion results present (a suite that failed to run has none, and its message is kept), exactly one result per expected id and any other test only `pending`, outcome and failure messages consistent, exit 0 or 1 agreeing with the outcomes. A failure's type is the first line's exception name (Jest 24 reports matcher failures as `Error`, thrown errors by their type); its location is the topmost stack frame in a patch file, with the test's own name as the function, since Jest test bodies are anonymous callbacks. No captured output is reported (Jest's JSON has none). A witness request is answered `unavailable` without running anything, as for Java.

## Acceptance and validation

Offline: parser and runner tests over real Jest 24.8.0 output captured on Node 8.17.0 in the `node8` image (`tests/unit/jest_reports/`): listing, matcher and thrown failures, a passing candidate, a syntax error and a non-test file, plus mutations for every refusal; the runner's argv, stage order, no-retry, and gate evidence (`run_evidence`) through the existing composition. Live: the node8 toolchain gate runs the runner's discovery and execution argv on the fixture in an OpenShell sandbox (`node_runner_commands`). A real Jest case through the runner in fresh sandboxes at both commits follows once the case harness exists for JavaScript.

## Decisions and open questions

Listing by a never-matching name pattern rather than `--listTests` (which names files, not tests) or a static parse of the file; it is the only Jest 24 mode that names tests without running them. The framework matrix row (`jest`, exact versions that ran, images `node-8.17.0-npm`) is added with the image row after the live gate, naming only Jest 24.8.0 until a case's own Jest version runs. Plan: [PLAN-0070](../plans/PLAN-0070-jest-runner.md).
