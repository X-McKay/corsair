---
id: SPEC-0058
kind: spec
title: Ruby 3.1 toolchain image
status: draft
updated: 2026-10-13
related: [SPEC-0042, SPEC-0007, SPEC-0045, SPEC-0046, PLAN-0063]
---

# Ruby 3.1 toolchain image

## Goal and scope

Al's goal (2026-10-13) is to run every benchmark case end to end, with Corsair adapting to each case's runtime rather than changing the project. SPEC-0042's report (`benchmarks/runtime-requirements.md`) suggests a Ruby 3.1 row for 4 Ruby cases whose declared runtime ranges all contain 3.1: CVE-2023-22794 (rails, `>= 2.7.0`, Minitest 5.15.0 locked, Bundler 2.3.14 locked), CVE-2025-27610 (rack, `>= 2.4.0`, Minitest `~> 5.0`), CVE-2023-36823 (sanitize, `>= 2.5.0`, CI up to 3.1, Minitest `~> 5.14.4`) and CVE-2024-21510 (sinatra, `>= 2.7.8`, Minitest `~> 5.0`). This spec adds the image, its fixture and its toolchain gate. Not in scope: the Minitest runner and report parser and the `minitest` framework admission (the second PR in this thread, PLAN-0063), RSpec, the two Ruby cases that need Ruby 2.4 to 2.7 (CVE-2020-10187, CVE-2017-0889), and the 4 Ruby cases without a pinned commit.

No case becomes supported from this PR alone: the detector needs a framework row naming the image, and a framework row needs a Corsair runner (SPEC-0042). The image unblocks the runtime component of the 4 cases above; the runner PR unblocks their test framework.

## Boundaries and design

`deploy/qualification/toolchains/ruby31` is `FROM` the official `ruby` image by index digest. Measured in the pinned image: Ruby 3.1.7p261, RubyGems 3.3.27, Bundler 2.3.27 (default gem), and the bundled gems Minitest 5.15.0, test-unit 3.5.3 and rake 13.0.6 under `/usr/local/lib/ruby/gems/3.1.0`. The full (buildpack-deps) variant is used rather than `-slim`, because the cases' gems build native extensions during setup: the Rails case's `Gemfile.lock` holds mysql2 0.5.3, pg 1.3.0, sqlite3 1.4.2, nio4r, bcrypt, puma, websocket-driver and others, and sinatra's Gemfile names eventmachine, redcarpet, rdiscount and yajl-ruby. The sandbox cannot install system packages, so the compiler and the client library headers have to be in the image.

The image adds only the fixture: `Gemfile` (`gem "minitest", "5.15.0"`), a `Gemfile.lock` written by `bundle lock --local` in the pinned image (Bundler 2.3.27, platform `x86_64-linux`), and `test/native_test.rb` with `NativeTest#test_native_roundtrip` and `NativeTest#test_native_runtime` (asserting Ruby 3.1 and Minitest 5.15.0). Nothing is fetched during the build (`docker build --network=none`), so there is no download to hash-pin; the base digest pins everything. Ruby, Bundler and the gems live under `/usr/local`, which the sandbox policy already mounts read-only; only `/opt/corsair-fixture` is added.

Minitest has no native XML report. The trusted control and the gate read its verbose output (`Class#name = <seconds> s = .` per test and the final `N runs, N assertions, N failures, N errors, N skips` line) and require exactly the two fixture tests, both passing. The gate, as for the sibling images, runs offline in the sandbox: version check; the fixture through `bundle exec` with a frozen lockfile; missing gem (`bundle install --local` exits 7 with Bundler's "Could not find gem ... in cached gems"); no discovery (`-n` matching nothing: Minitest exits 0 and reports `0 runs`, so a runner has to treat zero runs as no discovery); syntax error; assertion failure (`Expected: 1` / `Actual: 2`, exit 1). It also confirms the image's `GEM_HOME` (`/usr/local/bundle`) is not writable in the sandbox.

Findings for the runner PR and setup: project gems cannot go into `GEM_HOME`, so setup installs them under the workspace; with `BUNDLE_PATH` set, Bundler no longer sees the bundled Minitest, so a project then installs its own Minitest from the registry (checked in the pinned image). No registry install is part of this gate; registry egress during setup is SPEC-0026's and the Python gate's ground.

## Acceptance and validation

Offline: `make test-config`; the trusted control and the gate's offline sequence run against the image built locally with Docker (an image-only check, not sandbox qualification). Live on RIG0: `make toolchain-images` and `make toolchain-images-load` for `ruby31`, then the `ruby31` toolchain gate on a fresh admitted kind node. The `ruby-3.1-bundler` matrix row (`runtime: {name: ruby, version: 3.1.7}`, `tools: {bundler: 2.3.27}`) is added only after that gate passes, together with the qualification report entry. A real case through a Corsair runner belongs to the runner PR.

## Decisions and open questions

One image per runtime version (SPEC-0042). Ruby 3.1.7 is the last 3.1 release (3.1 is end of life upstream); no newer 3.1 patch will need a bump. The fixture locks the bundled Minitest 5.15.0, which is also the Rails case's exact lock; the framework row the runner PR adds lists only versions actually run. Plan: [PLAN-0063](../plans/PLAN-0063-ruby31-toolchain.md).
