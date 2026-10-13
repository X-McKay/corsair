---
id: PLAN-0071
kind: plan
title: One test runner core across languages
status: in_progress
updated: 2026-10-13
related: [SPEC-0065, PLAN-0066]
---

# One test runner core across languages

## Objective and dependencies

Implement [SPEC-0065](../specs/SPEC-0065-shared-test-runner-core.md) on branch `claude/toolchain-perl526-i5y3mp` (restarted from main 75f061b after #77 merged). Al chose "Merge, then refactor" on 2026-10-13. Jest (#83) and Minitest (#84) are converted after they merge.

## Steps

- [x] Runner core helpers; pytest, Maven and TAP runners on them.
- [x] `reports/admission.py`; one JUnit `testcase` reader for pytest and Surefire; TAP on the shared envelope and id checks.
- [x] `tests/qualification/image_case.py`; Java and Perl harnesses on it (Perl now runs the commit's blobs).
- [x] CVE-2023-31486 under Docker through the consolidated code.
- [ ] Draft PR; CI green.
- [ ] Jest and Minitest drivers once #83 and #84 are on main; their captures and Docker cases.

## Validation and progress

2026-10-13, cloud container. Runner, report and listing unit suites: 172 passed before and after, with no test changed. Harness smoke tests: 28 passed. The fixed TAP `LISTER`, `WRAPPER` and listing pattern compare equal to main's. `make test-config`: 1488 passed.

CVE-2023-31486 through `perl_image_case.py` on the shared harness (image `sha256:29cc7bca…`, commit blobs):
- vulnerable `7bdf71f`: control passed, security failed, 1.20 s;
- fixed `77f557e`: both passed, 0.85 s;
- cleanup confirmed for both.

These match the runs before the refactor. The Java harness was checked by its smoke test only: a VUL4J rerun needs the Maven setup, which the next live batch repeats.

## Decisions and next action

The per-framework checks after a run (empty report, wrapper exit 125, allowed exits) stay in each driver, because they are what genuinely differs. Next: the PR, then Jest and Minitest.
