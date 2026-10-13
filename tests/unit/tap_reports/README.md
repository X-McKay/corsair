# Real prove output on Perl 5.26.3

Recorded 2026-10-13 for [SPEC-0056](../../../docs/development/specs/SPEC-0056-perl526-toolchain.md) in the `perl526` toolchain image built from `docker.io/library/perl@sha256:c7e41279…` (`perl:5.26.3-buster`: Perl 5.26.3, TAP::Harness 3.38, Test::More 1.302073, GNU Make 4.2.1), with no network, as UID 10001, one fresh container per file. Files are the unedited stdout (stderr, which carries Test::More's failure diagnostics, is not included):

- `perl5.26.3-control.txt`: the trusted control, `perl Makefile.PL; make; prove -b -v t/` on the image's fixture (`deploy/qualification/toolchains/perl526`).
- The others: `prove -l -v t/` on the fixture's `Makefile.PL` and `lib/` with `t/native.t` changed on line 18 only (`native_runtime`'s assertion):
  - `failure`: `is(1, 2, 'deliberate_failure');` (exit 1, `Result: FAIL`).
  - `skip`: the assertion inside `SKIP: { skip 'not on this runtime', 1; ... }` (exit 0, `Result: PASS`).
  - `todo`: `is(1, 2, 'known_gap')` inside `TODO: { local $TODO = 'known gap'; ... }` (exit 0, `Result: PASS`).
  - `notests`: an empty `t/` (exit 0, `Result: NOTESTS`).

The skip, todo and notests runs all exit 0, and the skip and todo runs end in `Result: PASS`: a TAP consumer that trusts prove's exit status or summary alone would count them as passes. `tap_report` in `tests/qualification/prepare_toolchains.py` admits only the control.
