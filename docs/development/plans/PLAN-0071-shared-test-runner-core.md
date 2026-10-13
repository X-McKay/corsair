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
- [x] Draft PR #89; CI green on d826b25.
- [x] Exit agreement moved into `_completed` (review finding on #89); TAP keeps its own rule as an override.
- [x] Jest driver after #83 merged (main 86b37ce); its 71 capture tests unchanged; `node_image_case.py` on `image_case.py`.
- [ ] Minitest driver once #84 is on main; its captures and Docker case.

## Validation and progress

2026-10-13, cloud container. Runner, report and listing unit suites: 172 passed before and after, with no test changed. Harness smoke tests: 28 passed. The fixed TAP `LISTER`, `WRAPPER` and listing pattern compare equal to main's. `make test-config`: 1488 passed.

CVE-2023-31486 through `perl_image_case.py` on the shared harness (image `sha256:29cc7bca…`, commit blobs):
- vulnerable `7bdf71f`: control passed, security failed, 1.20 s;
- fixed `77f557e`: both passed, 0.85 s;
- cleanup confirmed for both.

These match the runs before the refactor.

Jest fold-in (main 86b37ce merged): Jest unit suite 71 passed unchanged; harness smoke tests 33 passed; `make test-config` 1567 passed. A Jest Docker rerun needs the Node case checkouts, which this container does not hold; the smoke test covers the harness wiring. The Java harness was checked by its smoke test only: a VUL4J rerun needs the Maven setup, which the next live batch repeats.

## Decisions and next action

The per-framework checks after a run (empty report, wrapper exit 125, allowed exits) stay in each driver, because they are what genuinely differs. Exit agreement is not one of them: it moved into the core so a new driver cannot skip it. Next: Minitest after #84 merges; then the environment agent's tap-harness admission as a separate PR.
