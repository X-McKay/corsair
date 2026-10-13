---
id: PLAN-0064
kind: plan
title: Minitest runner and report parser
status: in_progress
updated: 2026-10-13
related: [SPEC-0059, SPEC-0042]
---

# Minitest runner and report parser

## Objective and dependencies

Implement [SPEC-0059](../specs/SPEC-0059-minitest-runner.md) on main. The live steps need the `ruby31` image (PR #68, PLAN-0063) gated on RIG0 first.

## Steps

- [x] `RubyTestId`, `reports/minitest.py`, `adapters/minitest_runner.py` with fixed listing and run scripts.
- [x] Captured runner output for Minitest 5.14.4, 5.15.0 and 5.27.0 in the `ruby31` image; offline unit checks.
- [ ] After #68 and this PR merge: runner discovery and execution argv on the fixture inside `test_native_ruby31_toolchain`.
- [ ] RIG0: one real case (CVE-2025-27610 or CVE-2024-21510) at both commits in fresh sandboxes.
- [ ] `minitest` admission in the environment agent (assessed against its eval baseline), skill text, matrix framework row with the versions that ran, handoff.

## Validation and progress

2026-10-13, cloud container with local Docker (image-only): the runner's argv ran against the `ruby31` image built from PR #68 for Minitest 5.15.0 (bundled), 5.14.4 and 5.27.0 (installed into `vendor/bundle`, gem hashes matched rubygems.org); see `tests/unit/minitest_reports/README.md`. First 5.27.0 listing failed in `runnable_methods` (nil seed); fixed by setting `Minitest.seed` when unset, then all three versions listed and ran as expected. `tests/unit/test_minitest_runner.py`: 44 passed. `make test-config` on main 4efad96 plus this change: 1290 passed (first run failed the record check because SPEC-0058/PLAN-0063 are not on main yet; references dropped from `related`).

## Decisions and next action

The environment-agent admission waits for the real case, so the agent's prompt and eval are changed once, with evidence. Next: open the PR; gate integration after #68.
