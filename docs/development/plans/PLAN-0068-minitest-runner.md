---
id: PLAN-0068
kind: plan
title: Minitest runner and report parser
status: in_progress
updated: 2026-10-13
related: [SPEC-0063, SPEC-0042, SPEC-0058, PLAN-0063]
---

# Minitest runner and report parser

## Objective and dependencies

Implement [SPEC-0063](../specs/SPEC-0063-minitest-runner.md) on main after the `ruby31` image (PR #68, PLAN-0063, merged as a8a9e88). The live steps need the image gated on RIG0 first.

## Steps

- [x] `RubyTestId`, `reports/minitest.py`, `adapters/minitest_runner.py` with fixed listing and run scripts.
- [x] Captured runner output for Minitest 5.14.4, 5.15.0 and 5.27.0 in the `ruby31` image; offline unit checks.
- [x] Runner listing and run argv on the fixture inside `test_native_ruby31_toolchain` (`ruby_runner_commands`), checked image-only.
- [x] Image row `ruby-3.1-bundler` and framework row `minitest` (`==5.14.4 || ==5.15.0 || ==5.27.0`) in `deploy/runtime-matrix.yaml` as `evidence: image-only` (staged unit-test rows removed): the four Minitest cases select the image only with the runner row, image-only; the two RSpec cases stay unsupported.
- [x] Docker harness refuses image tags and dirty checkouts or overlay directories, as #74 does for Java.
- [x] Image-only real case under Docker: CVE-2025-27610 (rack) at both commits through `tests/qualification/ruby_image_case.py`.
- [ ] Sandbox run of a real case in the milestone gate batch; flips both rows to `live`.
- [ ] Rack CVE-2025-27610 through the chain end to end once the model server is free (CI case replay deferred by Al, 2026-10-13 15:43Z, until end-to-end runs are on the board).
- [x] `minitest` admission in the environment agent and skill text (#101, see note below); live environment eval pending.
- [ ] Handoff.

## Validation and progress

2026-10-13, cloud container with local Docker (image-only): the runner's argv ran against the `ruby31` image built from PR #68 for Minitest 5.15.0 (bundled), 5.14.4 and 5.27.0 (installed into `vendor/bundle`, gem hashes matched rubygems.org); see `tests/unit/minitest_reports/README.md`. First 5.27.0 listing failed in `runnable_methods` (nil seed); fixed by setting `Minitest.seed` when unset, then all three versions listed and ran as expected. `tests/unit/test_minitest_runner.py`: 44 passed. `make test-config` on main 4efad96 plus this change: 1290 passed (first run failed the record check because SPEC-0058/PLAN-0063 are not on main yet; references dropped from `related`).

2026-10-13, image-only real case (cloud container, local Docker, image built from PR #68's `ruby31` source through mirror.gcr.io by the same base digest): CVE-2025-27610, overlay `benchmarks/cases/rack-static/test/corsair_static_test.rb`. `setup` (network) ran `bundle install` per commit into a case bundle directory, resolving Minitest 5.27.0 and minitest-global_expectations 1.0.2 (93-line lockfile, same for both commits); `run` (`--network=none`, capability-dropped, as the host user like the Java harness: root in this container, which RIG0 does not share) drove `MinitestRunner` with prefix `env BUNDLE_FROZEN=true BUNDLE_PATH=/bundle/gems bundle exec /usr/local/bin/ruby`:

| Commit | Discovery | Control | Security | Failure location | Seconds | Cleanup |
| --- | --- | --- | --- | --- | --- | --- |
| 2db5cfb (vulnerable) | both listed | passed | failed (`Minitest::Assertion`, body was the test file itself: the traversal served it) | `test/corsair_static_test.rb:27`, `test_does_not_serve_files_outside_urls` | 1.39 | workspace and container confirmed |
| 50caab7 (fix) | both listed | passed | passed | | 1.29 | workspace and container confirmed |

2026-10-13, after #68 merged (branch restarted from main a8a9e88): records renumbered from SPEC-0059/PLAN-0064 (taken on other branches). The gate's Ruby steps including the new runner argv passed against the image under Docker (listing both fixture tests, both passed; `GEM_HOME` write gives EROFS under Docker where Landlock gives EACCES). CVE-2025-27610 rerun through the guarded harness with the image config id `sha256:751591eb…`: same outcomes (vulnerable: control passed, security failed; fix: both passed; cleanup confirmed). A tag is refused.

2026-10-13, review of 187a24f: setup now installs a committed `Gemfile.lock` frozen (`BUNDLE_FROZEN=true`) and fails if the installed lock differs; `setup.json`/`run.json` record `lock` (`committed` or `resolved`), lock digests, `-I` directories and setup's docker flags with environment values redacted. Checked under Docker: a committed-lock fixture installed with identical digests (8ac8a7a5…); the same fixture with the Gemfile changed and the lock not regenerated failed setup (Bundler exit 16, frozen). Rack (no committed lock, `resolved`) rerun at both commits: identical lock (8c8e9bc6…, Minitest 5.27.0) and identical outcomes. `make test-config` after merging main 497db9f: 1426 passed.

2026-10-13, Codex and review findings at 344cb6b: (1) non-string `class`/`name`/`outcome` raised `TypeError` past the typed result; reproduced (4 new tests failed), fixed, 49 unit tests pass. (2) Discovery accepted helper-defined or inherited `test_*` methods when the patch reopens or subclasses a repository class; reproduced under Docker (listing returned `ReopenedTest#test_from_helper` and `ChildTest#test_inherited`), fixed by keeping only methods whose `source_location` is the loaded patch file; after the fix only the patch's methods list, so discovery refuses. (3) The harness now checks the bundle's `Gemfile.lock` against setup's digest before the run container starts; a tampered lock is refused. Rack rerun at both commits and the gate's Ruby steps under Docker: unchanged outcomes.

Not run: sanitize CVE-2023-36823 (the benchmark records only its fix revision), sinatra CVE-2024-21510, Rails CVE-2023-22794 (component directory and database setup still to check).

2026-10-13, environment-agent admission of `jest` and `minitest` (branch from main 165afac), generalised with `tap-harness` as file-unit frameworks in `agents/environment/frameworks.py`: the baseline id is one plain repository-relative test file, one rule (`OneFile`) checks that the baseline command runs exactly that file under the runner with no filtering, listing or code-loading option, and each framework reads its own result. Jest needs `--json --runTestsByPath` and admits the JSON report only with one suite, every test passed and no pending, todo or failed test; Minitest needs `ruby` (or `bundle exec ruby`) on the one file without `-n/--name/-e/--exclude` and exactly one summary line with at least one run and no failure, error or skip. Checked against output captured offline in the `node8` (Jest 24.8.0) and `ruby31` (Minitest 5.15.0) images (`tests/agents/framework_outputs/`); prompt `environment-v6-file-unit-frameworks`; `make eval AGENT=environment` scripted 16/16; live eval waits for the model server.

2026-10-13, review fix on #101: a Minitest baseline command now allows only `-I` and `-r` before the file (an allow-list, as for prove), since `ruby -Csub <file>` runs `sub/<file>` and `ruby -s other.rb <file>` runs `other.rb`; Jest's `-c/--config` is refused, since an inline or file config can change test matching, roots and reporters. Tests for each evasion in `tests/agents/test_environment.py`.

2026-10-13, Ruby path for the chain (no model; branch from main 59492d2): gaps beyond the Node thread's shared entry point listed in `/mnt/project-files/handoffs/ruby-rack-chain-gaps.md` (project files). Added `agents/test_authoring/ruby.py`, a bounded pure-Python reader for the assertion lines of one Minitest method (skips comments, strings, heredocs, `%` literals, symbols, labels and regular expressions; refuses `=begin`, `__END__` and endless methods), used by authoring finalization for `RubyTestId`s. Checked against Prism (Ruby 3.3) over every `test_*.rb`/`*_test.rb` in the container: 7,377 methods identical, 0 differing, 925 refused (all endless definitions in Minitest's own tests). Authoring skill: one Minitest sentence on `Minitest::Assertion` and `assert_raises`; prompt `test-authoring-v8`; `make eval AGENT=authoring` scripted 18/18. Rack manifest `benchmarks/cases/rack-static/case.yaml` (agent issue text from the fix's code change, not yet second-reviewed; expected outcomes observed image-only). Witness for Ruby is open (decision card in the thread); the self-observation admission check for Ruby lands with it.

## Decisions and next action

The environment-agent admission waits for the real case, so the agent's prompt and eval are changed once, with evidence. Under the lighter path (Al, 2026-10-13 13:55Z) the rows landed as `image-only` from the Docker evidence above; the milestone gate batch for `ruby31` (with the runner argv) flips them to `live`. Next: the rack case end to end through the chain (the environment agent admits `minitest` since #101).
