---
id: SPEC-0061
kind: spec
title: Perl TAP runner
status: draft
updated: 2026-10-13
related: [SPEC-0056, SPEC-0042, SPEC-0007, SPEC-0045, PLAN-0066]
---

# Perl TAP runner

## Goal and scope

[SPEC-0056](SPEC-0056-perl526-toolchain.md) adds the `perl526` image; the six Perl cases it covers still select nothing, because SPEC-0042 needs a `tap-harness` framework row and a framework row needs a Corsair runner. This spec adds that runner: a native Test::More runner beside `adapters/pytest_runner.py` and `adapters/maven_runner.py`, its report parser, and the staged framework row scoped to the `perl526` image row.

Not in scope: the environment agent admitting `tap-harness` (its framework list and setup skill change behaviour that needs its own eval baseline, a follow-up); CPAN dependency installation through OpenShell policy; Dist::Zilla projects with no `Makefile.PL` (CPANSA-Dancer2-2018-01 and CVE-2026-8450 keep only `dist.ini`, so they need `dzil build` or the CPAN release tarball, decided in a follow-up); Module::Build; witnesses (no Perl probe exists, so a witness request is reported `unavailable` and nothing runs); the matrix rows, which land after the live gate batch.

## Boundaries and design

**Ids.** `path/to/file.t#subtest` (`ports.test_runner.PerlTestId`): a relative `.t` path with no `..`, and a Perl identifier. Control and security must be two distinct top-level subtests of the one patch file, so one TAP stream carries both outcomes, as one Python class or one Java class does for the sibling runners.

**Operator prefix.** `TapRunnerConfig.command` is an absolute Perl followed only by relative `-I<dir>` options (for example `-Iblib/lib -Iblib/arch -Ilib`); the discovery command the caller passes must equal it. Nothing agent-supplied reaches argv except the file path, which is a patch file and cannot start with `-`. Fixed `/bin/sh` wrappers take the workspace root, Perl argv and file as positional arguments, change directory, and merge stderr into stdout, which is where Test::More writes its diagnostics.

**Discovery.** TAP has no listing mode. Discovery runs a fixed operator program with `perl -e` that replaces `Test::More::subtest` with a recorder printing `corsair-subtest<TAB>name`, loads the file with `do`, and leaves through `POSIX::_exit` so Test::Builder's end-of-run checks do not fire. Subtest bodies do not run; file-level code does, as pytest's collection imports a module. The listing is accepted only with exit 0, no top-level TAP result line (a test outside a subtest ran), no duplicate names, and exactly the two requested names; otherwise the run stops at the discovery layer and nothing executes. This is bespoke, so the native gap is recorded: Test::More and TAP::Harness 3.38 offer no way to enumerate subtests without running them. Rejected: compile-only discovery (`perl -c`, which finds a misnamed subtest only after bodies ran) and running the file twice (bodies and their side effects repeat). The choice was put to Al on a decision card; work proceeds on the recommended listing preload until he answers.

**Execution and admission.** One run of `perl <prefix> <file>` in a fresh workspace, no retries. The stdout is stored as the report, then `reports/tap.py` admits it: each top-level result belongs to the `# Subtest:` header before it, and the stream is refused for a bail-out, any todo at any depth, a skip-all plan, a top-level result outside a subtest, non-sequential numbers, an unexpected, duplicate or missing subtest, or a plan other than exactly two. A subtest with a skip inside it is `skipped`, never `passed` (prove calls that a pass; SPEC-0056). `not ok` is `failed`, with the first `at FILE line N.` inside the patch file and the got/expected text; a subtest that dies is `error` (`No tests run for subtest`). The exit status must agree: Test::More exits with the number of failures, or 255 when the file died. A refused stream keeps its stored report with no claims (`invalid_report`), and the gates then see no admitted claim.

**Framework row.** Staged in the selection test, not in `deploy/runtime-matrix.yaml`: `tap-harness` with versions `==1.302073` (the Test::More the runner was measured with, which is what writes the TAP and decides the exit status; prove's harness version does not affect the runner, which does not call prove), runner `src/corsair/adapters/tap_runner.py`, images `[perl-5.26-make]` (the image row), records SPEC-0056 and SPEC-0061. With it, the six cases select `perl-5.26-make` at both revisions; selection is not execution, and the two Dist::Zilla cases still cannot be built.

## Acceptance and validation

Offline: unit tests over real Perl 5.26.3 output captured in the image (`tests/unit/tap_reports/runner/`: pass, fail, die, a die in the control, inner skip, skip-all, todo, bail-out, missing plan, a test outside a subtest, a syntax error; each with its listing and both exit statuses), runner orchestration with the existing fake ports, config refusals, and `run_evidence` from a TAP run. Image-only under Docker (the agreed check for a runner change; not sandbox qualification): `tests/qualification/perl_image_case.py` runs the runner on a real checkout in one `--network=none`, capability-dropped `perl526` container, with dependencies installed by a separate `cpanm --installdeps --notest` setup container. CVE-2023-31486 ([test](../../../benchmarks/cases/http-tiny-verify-ssl/README.md)) must show control passing on both revisions, security failing on the vulnerable one and passing on the fix, with cleanup confirmed. Live: the next kind gate batch before the rows land.

## Decisions and open questions

The parser derives from the stream, not prove's summary, because prove passes skips, todos and empty runs. Environment-agent admission and Dist::Zilla handling are follow-ups named above. Al's answer on the discovery card may change the discovery section. Plan: [PLAN-0066](../plans/PLAN-0066-perl-tap-runner.md).
