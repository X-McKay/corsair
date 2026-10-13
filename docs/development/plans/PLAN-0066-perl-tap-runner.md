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
- [x] Environment-agent admission of `tap-harness` (framework entry, skill line, prompt `environment-v5-tap-harness`, selection mapping); scripted eval 16/16; live eval waits for the model server.
- [ ] Follow-ups: Dist::Zilla cases; the remaining three `Makefile.PL` cases under Docker; matrix rows after the kind gate batch.

## Validation and progress

2026-10-13, cloud container, local Docker (not qualification). Captures: each `tests/unit/tap_reports/runner/<name>.t` run in the `perl526` image as UID 10001 with `--network=none`, once with `perl` (`.tap`) and once through the listing program (`.list`), exit statuses in `exits.json`. They confirm the parser's rules: a die inside a subtest prints `not ok N - No tests run for subtest "NAME"` and exits 255; a missing `done_testing` exits 254; a failed subtest exits with the failure count; a skip, a skip-all and a todo all exit 0; the listing program exits 0 without running bodies, 2 on a syntax error, and 255 on a file-level bail-out.

CVE-2023-31486 through `perl_image_case.py` with HTTP-Tiny from upstream (setup: `cpanm --installdeps --notest`, only core prerequisites; build: `Makefile.PL` and `make` offline): vulnerable `7bdf71f` gave control `passed`, security `failed` (`got: '0'`, `expected: '1'` at `t/corsair_verify_ssl.t` line 23), in 1.02 s; fixed `77f557e` gave both `passed`, in 0.95 s. Workspace and container cleanup confirmed for both. Evidence stayed in the container's scratch area (`run.json`, stored reports), not checked in. Rerun on main c31997c after adding #74's guards (image config id `sha256:29cc7bca…`, clean checkouts): the same outcomes (vulnerable 1.13 s, fix 1.04 s), cleanup confirmed; a tag is refused before anything runs.

`pytest tests/unit/test_tap_runner.py`: 27 passed. `make test-config`: 1305 passed on the #65 branch head 9fa9a7a plus this change; 1314 on main c31997c.

2026-10-13, environment-agent admission (branch restarted from main 164a556 after #89): the agent's framework table gains `tap-harness`. Its baseline unit is one repository-relative `.t` file, as `prove --dry` prints it (the runner's `file.t#subtest` ids stay runner-only). The baseline command must run `prove --norc` on exactly that file (`--norc` keeps a project `.proverc` from adding options unseen), with no dry run, saved state, `--exec`, archive, rules, other harness, plugin (`-P`) or module (`-M`), and the id refuses `.`/`..` segments (review of 511c4dc); admission needs verbose output (`ok N` lines), `Files=1, Tests=N>0`, `Result: PASS`, and no skip, todo, skip-all, `1..0` or `not ok` line, because prove's own summary passes all of those. Checked against prove 3.38 output captured in the `perl526` image (passing, skipped, todo, nested skip-all, skip-all file) and against HTTP-Tiny `77f557e` built offline in the image: `prove --dry -b t/` lists `t/000_load.t`, and `prove --norc -bv t/000_load.t` is admitted. `nodes/runtime/environment.py` maps the `tap-harness` row to it, so a Perl selection admits a `tap-harness` ready result and nothing else. `make eval AGENT=environment` (scripted, development set): 16/16 clean, no earlier scripted run to compare. The frozen set has no Perl case, and the live eval against the model server was not run here (one live user at a time); it is the remaining measurement for this prompt change.

## Decisions and next action

Listing preload is implemented as recommended on the decision card; if Al picks another option, discovery changes and the parser and execution stay. The environment agent's framework list now includes `tap-harness`; the prompt identity moved so its live baseline is compared, not mixed. Next: the draft PR and CI; the image-case harness takes the same clean-checkout and config-id checks as #74 does for the Java harness.
