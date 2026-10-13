---
id: PLAN-0061
kind: plan
title: Perl 5.26 toolchain image
status: in_progress
updated: 2026-10-13
related: [SPEC-0056, SPEC-0042, PLAN-0049, PLAN-0050]
---

# Perl 5.26 toolchain image

## Objective and dependencies

Implement [SPEC-0056](../specs/SPEC-0056-perl526-toolchain.md) on branch `claude/toolchain-perl526-i5y3mp`. It stacks on PR #51 (JDK 8: per-image source hashes, `--language`, one gate per image with its own evidence directory) and PR #55 (CPython 3.7: `TOOLCHAINS`/`--toolchain`, `PYTHONS`), which both change `prepare_toolchains.py` and `test_toolchains.py`. The merge commit keeps #51's one-gate-per-image structure and #55's selection, with `python37` as its own gate; whichever of #51 and #55 merges second resolves the same conflict on main, and this branch then takes main's version and re-applies only the Perl lines. The live gate needs the kind cluster on RIG0, after the JDK 8, CPython 3.7 and #49 holders. Both have merged (main 93a0fab). The TAP runner is the next PR and does not wait for the live gate.

## Steps

- [x] Image source, fixture, preparation (`BASES`, `PERLS`, control, offline build), `tap_report`.
- [x] Gate `test_native_perl526_toolchain` with the TAP diagnostics; selection and one-gate-per-image check.
- [x] Captured real prove output and `tap_report` tests; staged `perl-5.26-make` row in the selection test.
- [x] Merge on offline review and CI (process change approved by Al 2026-10-13 11:59Z; Al's word to merge after #51, 12:20Z).
- [ ] RIG0: build, load and gate on a fresh kind node, in the batch run before rows land.
- [ ] Evidence-only follow-up PR: the `perl-5.26-make` matrix row and the qualification report entry from the gate evidence.
- [x] Next PR: TAP runner and report parser ([SPEC-0061](../specs/SPEC-0061-perl-tap-runner.md)), `tap-harness` framework row on this image, a real case at both commits under Docker.

## Validation and progress

2026-10-13, cloud container (Docker 29.8.2 daemon started in the container; not qualification). `docker pull perl:5.26.3-buster` gave index `sha256:c7e41279…`; upstream provenance from docker-library/official-images `e4020732` (`GitCommit: 311f0536`, `Directory: eol/5.026.003-main-buster`). In the image with `--network=none` as UID 10001: `perl` 5.26.3, GNU Make 4.2.1, `prove` TAP::Harness 3.38, Test::More 1.302073, ExtUtils::MakeMaker 7.24, App::cpanminus 1.7044; `/usr/bin/python3` is Debian's 3.7, so the CPython 3.12 witness probe cannot run there.

`docker build --network=none` of the context succeeded; the control command passed `tap_report`. The gate body `perl_offline` ran against a container of the image with `docker exec` standing in for the OpenShell SDK and passed all steps (report SHA-256 `8e7d3b4d…`). Real prove outputs for pass, failure, skip, todo and no tests are in `tests/unit/tap_reports/`; skip and todo exit 0 with `Result: PASS`, no tests exits 0 with `Result: NOTESTS`.

Selection over PR #61's `benchmarks/runtime-requirements.json` (both revisions of each of the six Perl cases) with the staged row: every one is `unsupported` needing only `tap-harness`; with a staged `tap-harness` framework row on this image every one selects `perl-5.26-make`. Script only, not checked in, because the report is on #61's branch.

`make test-config`: 1258 passed on the stacked base (main 4a75870 plus #51 and #55) before the Perl changes; 1270 passed with them, after merging main 0ad9900.

## Decisions and next action

No framework row in this PR: a framework with no Corsair runner is a gap, not a row (base-image skill step 6). Under the 2026-10-13 process change an image PR merges once offline review and CI are clean, with no matrix row; the kind gate runs once in the batch before rows land and the row follows in a small evidence-only PR. Main merged at 93a0fab (#51 and #55 on main), so the diff is only the Perl image work. Next: the TAP runner PR.
