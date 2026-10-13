# Real Jest output on Node 8

Recorded 2026-10-13 for [SPEC-0057](../../../docs/development/specs/SPEC-0057-jest-runner.md) in the `node8` toolchain image built image-only in the cloud container (upstream `node@sha256:c9025a77…`, Node 8.17.0; Jest 24.8.0 from the fixture lockfile, offline), no network, project at `/sandbox/src` with the fixture `package.json` and the test file at `test/corsair.test.js`. Each `*.json` is the unedited file Jest wrote for `--json --outputFile`, which the runner's wrapper prints as stdout, for `node node_modules/jest/bin/jest.js --ci --runTestsByPath test/corsair.test.js` plus:

- `*-listing.json`: `--testNamePattern '(?!)'` (matches no name: every test reported `pending`, no test body or hook ran; checked with marker files).
- `*-run.json`: `--testNamePattern '^(?:corsair_control|traversal corsair_security|corsair_security)$'`.

Test files: `baseline.test.js` (security test fails on a matcher, exit 1), the same with `'readme.txt'` for `'../etc/passwd'` (`candidate-run`, exit 0), `thrown.test.js` (security test throws `TypeError`, exit 1), a file with a syntax error (`syntax-listing`, exit 1, `Test suite failed to run`, no assertion results), and `test/other.js`, which Jest's default `testMatch` does not select (`nontest-listing`, exit 1, no test results).
