---
id: PLAN-0066
kind: plan
title: Perl TAP runner
status: in_progress
updated: 2026-10-13
related: [SPEC-0061, SPEC-0056, PLAN-0061]
---

# Perl TAP runner

## Objective and dependencies

Implement [SPEC-0061](../specs/SPEC-0061-perl-tap-runner.md). It needs the `perl526` image from PR #65 ([PLAN-0061](PLAN-0061-perl526-toolchain.md)), whose captured TAP and `tap_report` it builds on, so it is a second PR after #65 merges, pushed to the same thread branch `claude/toolchain-perl526-i5y3mp` restarted from main. Under the 12:00Z process change, a runner change is checked image-only under Docker; the kind gate runs once in the batch before the Perl rows land.

## Steps

- [x] `PerlTestId`, `reports/tap.py` (`parse_tap`), `adapters/tap_runner.py` (listing discovery, one execution, claims).
- [x] Real Perl 5.26.3 captures for the runner (`tests/unit/tap_reports/runner/`) and unit tests.
- [x] Image-case harness `tests/qualification/perl_image_case.py`; CVE-2023-31486 test file under `benchmarks/cases/http-tiny-verify-ssl/`.
- [x] CVE-2023-31486 under Docker at both revisions.
- [x] Staged `tap-harness` framework row (`==1.302073`, images `[perl-5.26-make]`).
- [ ] Al's answer on the discovery decision card (listing preload recommended and implemented).
- [x] #65 merged (main c31997c); branch restarted from main with the runner commit.
- [x] Draft PR #77; CI green; review ready with two optional notes (they ride the next code push).
- [ ] Follow-ups: environment-agent admission of `tap-harness` with its eval baseline; Dist::Zilla cases; the remaining three `Makefile.PL` cases under Docker; matrix rows after the kind gate batch.

## Validation and progress

2026-10-13, cloud container, local Docker (not qualification). Captures: each `tests/unit/tap_reports/runner/<name>.t` run in the `perl526` image as UID 10001 with `--network=none`, once with `perl` (`.tap`) and once through the listing program (`.list`), exit statuses in `exits.json`. They confirm the parser's rules: a die inside a subtest prints `not ok N - No tests run for subtest "NAME"` and exits 255; a missing `done_testing` exits 254; a failed subtest exits with the failure count; a skip, a skip-all and a todo all exit 0; the listing program exits 0 without running bodies, 2 on a syntax error, and 255 on a file-level bail-out.

CVE-2023-31486 through `perl_image_case.py` with HTTP-Tiny from upstream (setup: `cpanm --installdeps --notest`, only core prerequisites; build: `Makefile.PL` and `make` offline): vulnerable `7bdf71f` gave control `passed`, security `failed` (`got: '0'`, `expected: '1'` at `t/corsair_verify_ssl.t` line 23), in 1.02 s; fixed `77f557e` gave both `passed`, in 0.95 s. Workspace and container cleanup confirmed for both. Evidence stayed in the container's scratch area (`run.json`, stored reports), not checked in. Rerun on main c31997c after adding #74's guards (image config id `sha256:29cc7bca…`, clean checkouts): the same outcomes (vulnerable 1.13 s, fix 1.04 s), cleanup confirmed; a tag is refused before anything runs.

`pytest tests/unit/test_tap_runner.py`: 27 passed. `make test-config`: 1305 passed on the #65 branch head 9fa9a7a plus this change; 1314 on main c31997c.

## Decisions and next action

Listing preload is implemented as recommended on the decision card; if Al picks another option, discovery changes and the parser and execution stay. The environment agent's framework list is untouched, because changing it moves that agent's baseline. Next: the draft PR and CI; the image-case harness takes the same clean-checkout and config-id checks as #74 does for the Java harness.
