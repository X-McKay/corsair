---
id: SPEC-0056
kind: spec
title: Perl 5.26 toolchain image
status: draft
updated: 2026-10-13
related: [SPEC-0042, SPEC-0007, SPEC-0045, SPEC-0046, PLAN-0061]
---

# Perl 5.26 toolchain image

## Goal and scope

Al's goal (2026-10-13) is to run every benchmark case end to end on the runtime each case needs. SPEC-0042's report (with PR #61's repin of CVE-2023-31486 to the upstream HTTP-Tiny repository) finds six Perl cases whose build files allow Perl 5.26 and need GNU Make and the TAP harness: CVE-2018-12015, CVE-2018-25100, CPANSA-Dancer2-2018-01, CVE-2026-8450, CVE-2023-31486 and CVE-2026-15043. Every other Perl case is `not_acquired`. This spec adds one image, `perl526`, and its toolchain gate; the matrix row follows the live gate.

Not in scope: a Corsair TAP runner and report parser (the analogue of `adapters/maven_runner.py` and `adapters/pytest_runner.py`), which is a separate PR after this one; CPAN dependency installation during setup (registry dependencies through OpenShell policy, as `python_dependencies` does for pip); Module::Build and Dist::Zilla projects; witnesses, whose probe is CPython 3.12 only; other Perl versions.

## Boundaries and design

The image `deploy/qualification/toolchains/perl526` is `FROM` the official `perl:5.26.3-buster` index digest `sha256:c7e412792cb4f1a5b9b7a632c01a02fb469c615e6745279b4ae1821d03105bc7` (linux/amd64, created 2021-05-21). That tag is end of life: it was last built by docker-library/official-images `e4020732` from [perl/docker-perl `311f0536`](https://github.com/perl/docker-perl/tree/311f05366d91427d289740dd15fb9401dc4347ef/eol/5.026.003-main-buster) (Perl 5.26.3 source tarball SHA-256-checked, App::cpanminus 1.7044) and removed from the library on 2021-05-24, so the digest no longer moves and Debian buster receives no updates. The base already carries what the cases need, measured in the image with no network: Perl 5.26.3, GNU Make 4.2.1, TAP::Harness/prove 3.38, Test::More 1.302073 and ExtUtils::MakeMaker 7.24 (all core or base), so the image adds only the fixture, `HOME=/tmp` and user 10001, and builds with `--network=none`. Nothing is fetched, so there is no pin file.

The fixture at `/opt/corsair-fixture` is a MakeMaker distribution (`Makefile.PL` with `MIN_PERL_VERSION 5.026`, `lib/Corsair/Native.pm`, `t/native.t`) with two subtests, `native_roundtrip` and `native_runtime` (asserting the 5.26 series), the same shape as the JDK images' two methods. Preparation (`prepare_toolchains.py`) adds `perl526` to `BASES` and `PERLS`; its trusted control runs `perl Makefile.PL; make; prove -b -v t/` offline as UID 10001 and admits the run with `tap_report`.

TAP has no JUnit-style report file, so `tap_report` admits the verbose prove stream: exactly one plan, exactly the expected top-level subtests `ok` in order, no `not ok`, skip or todo line at any depth, and prove's `Files=1, Tests=N` and final `Result: PASS`. Exit status and prove's summary alone are not evidence: real 5.26.3 output shows exit 0 for an empty `t/` (`Result: NOTESTS`) and exit 0 with `Result: PASS` for a skipped subtest assertion and for a failing assertion inside a TODO block (`tests/unit/tap_reports/`). The TAP runner PR must keep that rule.

The toolchain gate `test_native_perl526_toolchain` (`TOOLCHAINS=perl526`) runs the fixture in an OpenShell sandbox with the identity policy plus `/opt/corsair-fixture` read-only (Perl lives under `/usr/local`, already read-only): versions; `perl Makefile.PL`, `make`, `make test` and `prove -b -v t/` admitted by `tap_report`; then the sibling images' offline diagnostics in TAP terms: missing module (`Can't locate Corsair/Absent.pm in @INC`, exit 1), no discovery (exit 0, `Result: NOTESTS`), compilation (`syntax error`, exit 1) and assertion (`Failed test 'deliberate_failure'` with got/expected, exit 1, and exit 2 through `make test`). There is no Corsair runner for Perl yet, so no runner argv is exercised.

The staged matrix row is `perl-5.26-make` (`runtime {perl, 5.26.3}`, `tools {make: 4.2.1}`). It is not added to `deploy/runtime-matrix.yaml` until the gate passes on RIG0. Even then the six cases stay `unsupported` with `tap-harness` named until the runner PR adds a `tap-harness` framework row scoped to this image; the detector reports `tap-harness` with any version, and which version that row names (the harness 3.38 that prove runs, or the project's own Test::More) is the runner PR's decision.

## Acceptance and validation

Offline: `make test-config`, including `tap_report` over the captured real outputs, the gate selection (`--toolchain perl526` selects exactly the Perl gate and every prepared image has exactly its own gate), and the staged row (the fixture's `Makefile.PL` selects `perl-5.26-make` once a TAP framework row exists, is `unsupported` naming only `tap-harness` without one, and a project needing Perl 5.28 is not routed to it). Local Docker (not qualification): image build with no network, control, and the gate body with `docker exec` standing in for the SDK. Live on RIG0: `make toolchain-images TOOLCHAINS=perl526`, `make toolchain-images-load TOOLCHAINS=perl526`, `make qualify-toolchain TOOLCHAINS=perl526` on a fresh admitted kind node; then the matrix row and report entry. A real case through the runner waits for the runner PR.

## Decisions and open questions

The EOL buster tag is the only official 5.26 image; a newer distribution would mean building Perl ourselves. The six cases also accept Perl 5.28 to 5.42 in places, but 5.26 is the one release all six allow (SPEC-0042's report), and one image per runtime version stays the rule. The PR stacks on #51 and #55 for per-image preparation, `--toolchain` selection and one gate per image. Plan: [PLAN-0061](../plans/PLAN-0061-perl526-toolchain.md).
