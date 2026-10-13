---
id: PLAN-0063
kind: plan
title: Ruby 3.1 toolchain image
status: in_progress
updated: 2026-10-13
related: [SPEC-0058, SPEC-0042, PLAN-0046, PLAN-0049, PLAN-0050]
---

# Ruby 3.1 toolchain image

## Objective and dependencies

Implement [SPEC-0058](../specs/SPEC-0058-ruby31-toolchain.md) with the `corsair-base-image` skill. Branch `claude/toolchain-ruby31-6f6z4l` builds on the JDK 8 (#51, per-image preparation and gates) and CPython 3.7 (#55, `TOOLCHAINS`/`--toolchain` selection) work; both are merged and main is merged in (93a0fab), so the PR diff is the Ruby change only. Live steps need RIG0 and the shared kind cluster, in the order JDK 8, CPython 3.7, #49's live chain, Perl 5.26, Node 8, then this thread.

## Steps

- [x] Image source: official `ruby:3.1.7-bookworm` by index digest, fixture `Gemfile`/`Gemfile.lock`/`test/native_test.rb`; `BASES`, trusted control, offline build.
- [x] Gate `test_native_ruby31_toolchain` (`TOOLCHAINS=ruby31`): versions, fixture, read-only `GEM_HOME`, missing gem, no discovery, syntax, assertion; selection test row.
- [ ] RIG0: build and load `ruby31` on a fresh admitted node; run the gate.
- [ ] After the gate passes: `ruby-3.1-bundler` matrix row with the measured versions, qualification report entry (tag, platform, index and manifest digests, upstream Dockerfile source commit, run table), handoff.
- [ ] Second PR: Minitest runner and verbose-output parser on the native runner contract (`adapters/native_runner.py`), offline parser check against real Minitest output for each version claimed, `minitest` framework admission and its framework row after a real case (CVE-2025-27610 or CVE-2024-21510) passes on RIG0.

## Validation and progress

2026-10-13, cloud container with a local Docker daemon (image-only, not sandbox qualification):

- Base: `docker.io/library/ruby:3.1.7-bookworm`, index digest `sha256:91627f55e8969006aab67d15c92fb930500ff73948803da1330b8a853fecebb5` (Docker Hub tag API, last updated 2025-03-26; the same digest from mirror.gcr.io), linux/amd64 manifest `sha256:78004237c5b503d0b5f5a9af7d6a1afff39163d316bf02b84d7f9022a0470812`. Docker Hub's anonymous pull limit was exhausted on this container's address, so the image was pulled through mirror.gcr.io by that digest; RIG0 pulls it from docker.io.
- Measured: Ruby 3.1.7p261, RubyGems 3.3.27, Bundler 2.3.27, bundled Minitest 5.15.0, test-unit 3.5.3, rake 13.0.6, Debian 12.10, gcc 12.2.0, make 4.3, libpq-dev, default-libmysqlclient-dev, libsqlite3-dev, libxml2-dev, libxslt1-dev, libyaml-dev, libffi-dev, libssl-dev.
- The `-slim` variant (`sha256:2704d8ee…`) was tried first and dropped: it has no compiler, and the Rails case's lockfile builds mysql2, pg and sqlite3 1.4.2 from source. In the full image, `gem install sqlite3:1.4.2 pg:1.3.0 mysql2:0.5.3` built and loaded all three as UID 10001 with a read-only root and a `/tmp` install directory (registry access through this container's proxy; image-only).
- `Gemfile.lock` written by `bundle lock --local` in the pinned image. `docker build --network=none` passed; the trusted control's command printed both tests and `2 runs, 4 assertions, 0 failures, 0 errors, 0 skips`.
- `ruby_offline` (the gate's sandbox sequence) ran end to end against the image with `docker run --read-only --tmpfs /tmp --user 10001` and a writable workspace mount, every assertion passing except the `GEM_HOME` write check, where Docker's read-only root gives `Read-only file system` instead of Landlock's `Permission denied`; the gate keeps the sandbox expectation (`expect_permission_denied`, as in the policy gate).
- With `BUNDLE_PATH` set, Bundler no longer sees the bundled Minitest (`Could not find minitest-5.15.0 in locally installed gems`): projects install their own Minitest during setup.
- `make test-config`: 1259 passed on the stacked branch, 1279 after merging main at 93a0fab (includes the collection-only selection test with the `ruby31` row).

## Decisions and next action

Full image over slim (native extensions; see SPEC-0058). No registry install in this gate: setup egress is qualified by the Python gate and SPEC-0026. Next: wait for the cluster turn after the Node 8 thread, then post the RIG0 paste; meanwhile build the Minitest runner as the second PR.
