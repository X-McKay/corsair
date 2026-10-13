---
id: PLAN-0068
kind: plan
title: Minitest runner and report parser
status: in_progress
updated: 2026-10-13
related: [SPEC-0063, SPEC-0042]
---

# Minitest runner and report parser

## Objective and dependencies

Implement [SPEC-0063](../specs/SPEC-0063-minitest-runner.md) on main. The live steps need the `ruby31` image (PR #68, PLAN-0063) gated on RIG0 first.

## Steps

- [x] `RubyTestId`, `reports/minitest.py`, `adapters/minitest_runner.py` with fixed listing and run scripts.
- [x] Captured runner output for Minitest 5.14.4, 5.15.0 and 5.27.0 in the `ruby31` image; offline unit checks.
- [ ] After #68 and this PR merge: runner discovery and execution argv on the fixture inside `test_native_ruby31_toolchain`.
- [x] Image-only real case under Docker: CVE-2025-27610 (rack) at both commits through `tests/qualification/ruby_image_case.py`.
- [ ] Sandbox run of a real case in the batch before the framework row lands (process of 2026-10-13: image PRs and runners are checked image-only; the kind gate is reserved for sandbox changes and the batch before a row).
- [ ] `minitest` admission in the environment agent (assessed against its eval baseline), skill text, matrix framework row with the versions that ran, handoff.

## Validation and progress

2026-10-13, cloud container with local Docker (image-only): the runner's argv ran against the `ruby31` image built from PR #68 for Minitest 5.15.0 (bundled), 5.14.4 and 5.27.0 (installed into `vendor/bundle`, gem hashes matched rubygems.org); see `tests/unit/minitest_reports/README.md`. First 5.27.0 listing failed in `runnable_methods` (nil seed); fixed by setting `Minitest.seed` when unset, then all three versions listed and ran as expected. `tests/unit/test_minitest_runner.py`: 44 passed. `make test-config` on main 4efad96 plus this change: 1290 passed (first run failed the record check because SPEC-0058/PLAN-0063 are not on main yet; references dropped from `related`).

2026-10-13, image-only real case (cloud container, local Docker, image built from PR #68's `ruby31` source through mirror.gcr.io by the same base digest): CVE-2025-27610, overlay `benchmarks/cases/rack-static/test/corsair_static_test.rb`. `setup` (network) ran `bundle install` per commit into a case bundle directory, resolving Minitest 5.27.0 and minitest-global_expectations 1.0.2 (93-line lockfile, same for both commits); `run` (`--network=none`, capability-dropped, as the host user like the Java harness: root in this container, which RIG0 does not share) drove `MinitestRunner` with prefix `env BUNDLE_FROZEN=true BUNDLE_PATH=/bundle/gems bundle exec /usr/local/bin/ruby`:

| Commit | Discovery | Control | Security | Failure location | Seconds | Cleanup |
| --- | --- | --- | --- | --- | --- | --- |
| 2db5cfb (vulnerable) | both listed | passed | failed (`Minitest::Assertion`, body was the test file itself: the traversal served it) | `test/corsair_static_test.rb:27`, `test_does_not_serve_files_outside_urls` | 1.39 | workspace and container confirmed |
| 50caab7 (fix) | both listed | passed | passed | | 1.29 | workspace and container confirmed |

Not run: sanitize CVE-2023-36823 (the benchmark records only its fix revision), sinatra CVE-2024-21510, Rails CVE-2023-22794 (component directory and database setup still to check).

## Decisions and next action

The environment-agent admission waits for the real case, so the agent's prompt and eval are changed once, with evidence. Next: open the PR; gate integration after #68.
