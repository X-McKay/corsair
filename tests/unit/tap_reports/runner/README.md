# Real Perl 5.26.3 TAP for the TAP runner

Recorded 2026-10-13 for [SPEC-0061](../../../../docs/development/specs/SPEC-0061-perl-tap-runner.md) in the `perl526` toolchain image (`perl:5.26.3-buster`, Test::More 1.302073), with no network, as UID 10001. Each `<name>.t` is the test file. `<name>.tap` is the unedited merged stdout and stderr of `perl -Ilib t/<name>.t`, which is the runner's execution. `<name>.list` is the same file under the runner's discovery program (`LISTER` in `src/corsair/adapters/tap_runner.py`). `exits.json` holds both exit statuses.

| File | What it shows |
| --- | --- |
| `pass`, `fail` | control and security subtests passing, then security failing with Test::More's got/expected (exit 1) |
| `die` | security dies: its result line becomes `No tests run for subtest "test_security"` and the file exits 255 with no plan |
| `controldie` | control dies, so security never runs (exit 255) |
| `innerskip`, `todo` | a skipped assertion and a failing TODO assertion inside a subtest that TAP reports as `ok` (exit 0) |
| `extra` | an assertion outside any subtest (exit 0; the lister prints it as a TAP result) |
| `bail`, `skipall`, `noplan` | `BAIL_OUT`, `skip_all` and a missing `done_testing` (exits 255, 0 and 254) |
| `syntaxerr` | a compile error (listing exit 2, run exit 255) |
