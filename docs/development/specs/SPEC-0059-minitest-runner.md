---
id: SPEC-0059
kind: spec
title: Minitest runner and report parser
status: draft
updated: 2026-10-13
related: [SPEC-0042, SPEC-0039, SPEC-0041, PLAN-0064]
---

# Minitest runner and report parser

## Goal and scope

The 4 Ruby benchmark cases the Ruby 3.1 image (SPEC-0058, PR #68) serves all test with Minitest: CVE-2023-22794 (rails, Minitest 5.15.0 locked), CVE-2023-36823 (sanitize, `~> 5.14.4`), CVE-2025-27610 (rack, `~> 5.0`) and CVE-2024-21510 (sinatra, `~> 5.0`; both resolve to 5.27.0 today, since Minitest 6 is outside `~> 5.0`). SPEC-0042 supports a case only when a framework row with a Corsair runner names the image, so the image unblocks nothing alone. This spec adds the runner and its report parser on the existing native runner contract (`adapters/native_runner.py`), the Ruby analogue of the Maven runner (SPEC-0039/SPEC-0041). Not in scope: environment-agent admission of `minitest` and the matrix framework row (after a real case passes on RIG0, PLAN-0064), RSpec and test-unit, spec-style (`describe`/`it`) test names, and a Ruby witness probe.

## Boundaries and design

Ids are `path/file.rb::Module::Class#test_method` (`ports.test_runner.RubyTestId`): a repository-relative patch file, a constant path, and a classic `Minitest::Test` method name. Spec-style names (`test_0001_does x`) hold spaces and are refused. Both ids are methods of one class in one patch file, as for Maven.

Minitest has no list-only mode and no machine-readable report, and the third-party reporter gems would change the project's dependencies. Two fixed operator Ruby scripts therefore use Minitest's public API only, run with `-e` after the operator's Ruby prefix (`MinitestRunnerConfig.command`, e.g. `env BUNDLE_FROZEN=true bundle exec /usr/local/bin/ruby -Itest -Ilib`, which must end in the absolute ruby binary plus options) in the workspace root, with the file, class and methods as positional arguments:

- Both scripts keep the real stdout for the runner and reopen fd 1 onto stderr, so test, helper, C-extension and child-process output never reaches the report; disable `Minitest.autorun` so loading the file runs nothing; load the file; and resolve the class by its constant path (refusing anything that is not a `Minitest::Runnable`).
- Discovery prints `Class#method` for each selected method among the class's `runnable_methods`. Class bodies and required helpers run (as pytest collection imports), no test body runs. The admitted discovery command must equal the operator prefix.
- Execution loads the project's own Minitest plugins first, then registers a recorder through Minitest's plugin hook, keeps only the tests' class in `Minitest::Runnable.runnables`, and calls `Minitest.run` once with `--seed 0` and an exact anchored name filter. It prints one `corsair-minitest-v1` JSON document (class, name, outcome, and for failures and errors the kind, exception class, message and first 50 backtrace lines) and exits 0 when Minitest reports success, else 1.

`reports/minitest.py` admits the report like Surefire XML: bounded bytes, UTF-8 JSON with duplicate keys refused, exactly the expected ids once each and nothing else, outcome and failure consistent, failure location from the innermost backtrace frame inside a patch file (Ruby 3.1 and 3.4 frame formats). The runner then requires the native exit to agree with the outcomes, as the Maven and pytest runners do. A missing report (load, Bundler or dependency failure) is an execution failure; nothing is retried. A witness request is answered `unavailable` without running anything.

## Acceptance and validation

Offline: `make test-config`, including the parser against the runner's own output captured in the `ruby31` image for Minitest 5.14.4, 5.15.0 and 5.27.0 (`tests/unit/minitest_reports/`: passed, failed, error and skipped results, helper stdout kept out of the report, other classes and unselected methods not run) and the orchestration cases of the Maven runner (inexact discovery never executes, inconsistent reports are retained not admitted, ids and prefix bounded). Live, after the image's gate (SPEC-0058) and in this thread's cluster turn: the runner's discovery and execution argv on the image fixture inside the toolchain gate, then one real case (CVE-2025-27610 or CVE-2024-21510) at its vulnerable and fix commits in fresh sandboxes. The framework row then names `ruby-3.1-bundler` with exactly the versions that ran (`==5.14.4 || ==5.15.0 || ==5.27.0` at most).

## Decisions and open questions

A small fixed reporter on Minitest's native plugin API instead of minitest-reporters or ci_reporter: those are project dependencies Corsair would have to add, and Al's direction is to run the project's own versions unchanged. Minitest 5.16+ orders `runnable_methods` with the run seed, which is unset outside `Minitest.run`; the listing script sets it when unset (found on 5.27.0). Rails runs its component tests from the component directory with its own helpers; whether the prefix and workspace root can express that is checked on the real case. Plan: [PLAN-0064](../plans/PLAN-0064-minitest-runner.md).
