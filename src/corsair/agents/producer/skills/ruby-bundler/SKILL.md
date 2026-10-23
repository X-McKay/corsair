---
name: ruby-bundler
description: Build and cover Ruby targets with Bundler and SimpleCov.
---
# Ruby / Bundler runtime

- Image: Debian-based **Ruby 3.2** with Bundler, Rake and SimpleCov 0.22.0 installed as gems. Python, `pytest` 9.0.3
  and `coverage` 7.13.4 are installed for the kernel-owned single-test Python driver.
- The submitted artifact is still a Python probe at `/work/.corsair/corsair_probe.py`, defining `CONTROL_PAYLOAD`,
  `EXPLOIT_PAYLOAD`, and a synchronous one-argument `run_target(payload)`. Use `subprocess` inside that function to
  invoke the genuine Ruby seam, e.g. `ruby bin/tool.rb ...` or `bundle exec ruby bin/tool.rb ...`; do not replace the
  Ruby target with a Python reimplementation or mocks.
- The kernel prepends `-r/work/.corsair/corsair_simplecov.rb` through `RUBYOPT`. Every Ruby target process therefore
  loads the trusted SimpleCov bootstrap before application code. Do **not** override `RUBYOPT`, call `SimpleCov.start`
  yourself, or move its output: the one accepted native report is `/tmp/corsair/ruby/.resultset.json`.
- The build script runs once with network and then the repository at `/work` is sealed read-only. A probe runs offline
  as uid/gid `1000`; only temporary output under `/tmp` is writable. Kernel `.corsair` support is root-owned/read-only. Run `bundle install` (or another
  minimal project dependency install) in the build script only when it is genuinely required; prefer the repository's
  lockfile and do not download or run setup scripts outside that replay.
- Native evidence is SimpleCov line coverage for the exact `target_file`; the Python driver's coverage report is not
  used for Ruby target lines. Choose executable source lines in the real Ruby method, and have both payloads traverse
  them.
- Use one invariant for control and exploit. If the expected malicious input causes a normal application exception,
  catch it inside `run_target` and assert the intended safe condition; only an assertion originating in the probe can
  establish a violation.
