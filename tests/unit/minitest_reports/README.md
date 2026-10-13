# Real Minitest runner output on Ruby 3.1.7

Recorded 2026-10-13 for [SPEC-0063](../../../docs/development/specs/SPEC-0063-minitest-runner.md) in the `ruby31` toolchain image (SPEC-0058: `docker.io/library/ruby@sha256:91627f55…`, Ruby 3.1.7, Bundler 2.3.27), one container per command, `--network=none`, `--read-only` root with a `/tmp` tmpfs, UID 10001, the project mounted at `/ws`. These are image-only captures, not sandbox runs.

The project is `project/` here (a `lib/widget.rb`, a `test/test_helper.rb` that requires `minitest/autorun` and prints to stdout, and `test/corsair_widget_test.rb` with `Widget::CorsairTest` plus an `OtherTest` class that must never run). Each version had its own `Gemfile` (`gem "minitest", "<version>"`):

- 5.15.0: Ruby 3.1's bundled gem, no `BUNDLE_PATH`.
- 5.14.4 and 5.27.0: installed by `bundle install` into `/ws/vendor/bundle` (gem SHA-256 matched rubygems.org: `f4716634…e7a7` and `2d3b17f8…77d5`), runner prefix with `BUNDLE_PATH=/ws/vendor/bundle`.

Runner prefix: `/usr/bin/env BUNDLE_FROZEN=true [BUNDLE_PATH=…] /usr/local/bin/bundle exec /usr/local/bin/ruby -Itest -Ilib`. Files are the unedited stdout of the runner's own argv (`MinitestRunner._discovery_argv` / `_execution_argv`):

- `*-listing.txt`: discovery for `test_control`, `test_security`, `test_error`, `test_skipped` and the absent `test_absent`.
- `*-report.json`: execution of the first four (passed, failed, error, skipped); native exit 1.
- `*-pass.json`: execution of `test_control` and `test_fixed`; native exit 0.

In every capture the helper's stdout line went to stderr, `OtherTest` and `test_unselected` did not run, and the listing named only selected methods that exist. The first 5.27.0 listing attempt failed (`srand': no implicit conversion of nil into Integer` in `runnable_methods`, because Minitest 5.16+ orders methods by the run's seed); the listing script now sets `Minitest.seed` when it is unset.
