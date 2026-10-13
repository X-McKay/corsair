---
id: SPEC-0074
kind: spec
title: Perl TAP on the image-only product route (setup, execution, witness, authoring reader)
status: accepted
updated: 2026-10-13
related: [SPEC-0061, SPEC-0065, SPEC-0033, SPEC-0040, SPEC-0073, PLAN-0088, PLAN-0087]
---

# Perl TAP on the image-only product route (setup, execution, witness, authoring reader)

## Goal and scope

`corsair run` refused every Perl request before setup with `no harness entry for the tap-harness framework yet`.
Runtime selection already resolved Perl corpus topics to the `perl-5.26-make` row and the `tap-harness` framework,
and the TAP runner, report admission and environment admission existed. Four generic pieces were still missing
between selection and an admitted gate:

1. The framework table (`corsair.investigation.frameworks`) had no `tap-harness` entry: no setup step, dependency
   location or runner config.
2. No operator witness recorder existed for Perl, so the planner had no facility to name (SPEC-0040) and no gate
   could reach `reproduces` or a calibrated `safe`.
3. TAP admission gave a failed Test::More assertion no failure type, so the gate called every security failure
   `unclassified_failure`.
4. Authoring's assertion reader treated any id it did not recognise as a pytest node id, so a Perl test file never
   passed authoring's final check.

Excluded: process-start, socket and other effect kinds (the same gap exists for Python); Test2::V0 subtests
(the lister and probe wrap Test::More's `subtest`); `dzil` projects; durable mode; OpenShell qualification.

## Boundaries and design

- **Table entry.** `tap-harness` uses `TapRunner` with the operator prefix `/usr/local/bin/perl -Ilib`. Setup runs
  the upstream image's own `cpanm --notest --installdeps --local-lib-contained .corsair-deps .` when the tree has a
  `cpanfile`, `Makefile.PL` or `Build.PL`. That is the same rule as pip and npm: the project's own manifest, registry
  access only in the setup container, no project test run. cpanm carries its own cpanfile reader, so a project whose
  requirements are all core fetches nothing. Run containers get `PERL5LIB=/tmp/work/.corsair-deps/lib/perl5` through
  a new `Harness.env` field. Unlike `-I`, `PERL5LIB` also adds the architecture directories XS modules install into.
  Lockfiles bound into the dependency identity are `cpanfile`, `cpanfile.snapshot`, `Makefile.PL` and `Build.PL`.
  The image is unchanged.
- **Witness recorder `perl_open` (`file_open`).** `nodes/witness_probe.pl` writes the same `corsair-witness-v2`
  record as the Python probe, so `witness_evidence`, calibration and the gate are shared. The only changes there:
  a capture names its probe digest, which must be one of the operator probes (`PROBES`), and the record's digest
  must equal the capture's. The runner starts the file as `perl -Ilib -e BOOTSTRAP <probe> <config> <file>`. The
  bootstrap installs `CORE::GLOBAL::open` before the test file compiles, wraps `Test::More::subtest` (with `goto`,
  so Test::More still reports the test's own line), and runs the file with `do`. At the start of each top-level
  subtest, the identified sub (by name, plus its package when the symbol is qualified, defined in the target file)
  is wrapped in every glob that holds it, imported aliases included.
  - Recorded: entries, returns or dies, file opens while a target call is on the stack, and failed opens with errno.
  - Counted apart: planned-file opens off the target after its first entry. They count as `body_planned` when the
    test file opens the planned file itself, and as `offstack_planned` otherwise.
  - Ignored: pipe, dup and in-memory opens.
  - Not observed: child processes, `sysopen`, XS code, and calls through code references taken before the subtest.
  - Tamper evidence: the record is `intact` only if the overrides and wrappers are still in place at the end. It
    is written once, with `O_EXCL|O_NOFOLLOW`, to an operator path outside the workspace. If that path already
    exists, the run exits 3.
- **TAP failure type.** A failed assertion inside a subtest is `not_ok` (TAP's own result word), and a subtest that
  dies stays `die`. The table's observation facility tells the planner both names.
- **Authoring reader.** `agents/test_authoring/perl.py` reads one Test::More subtest without Perl. It skips comments,
  strings, quote-like operators and matches, finds the one top-level `subtest NAME => sub {...}`, and returns the
  start lines of `ok`, `is`, `isnt`, `like`, `unlike`, `is_deeply`, `cmp_ok`, `can_ok`, `isa_ok`, `new_ok` and
  `fail` calls outside nested subs. Perl 5.26.3 reports a multi-line call at its first line. The reader refuses POD,
  `__END__`/`__DATA__`, heredocs, `format`, assertion-name definitions or aliases, and a missing or duplicated
  subtest, each with a reason. Authoring's input contract now admits `path.t#subtest` ids alongside pytest and
  Minitest. Main's `names_test_in` rule still ties each id to its approved file.
- **Shared code.** The witness record read-back moved from the pytest runner to `NativeRunner._read_witness`,
  because the TAP runner is its second consumer. Behaviour is unchanged.
- **`./` in locations.** `do` names the file `./t/x.t`, so `reports/tap.py` drops a leading `./` before matching a
  failure location to the patch's paths. Nothing else changes: outcomes, exit status and failure lines match an
  unprobed run.

## Acceptance and validation

- **Offline.** The real probe runs in the host's Perl on synthetic targets:
  - an observed open through an imported alias;
  - a calibrated `no_file_open`;
  - the test's own read counted apart;
  - an off-target planned open as `unknown`;
  - a same-named sub elsewhere is not the target;
  - a failed planned open as `unknown`;
  - a replaced override is not intact;
  - a pre-existing record path fails the run;
  - another probe or nonce is refused;
  - every recorded runner capture has the same exit status and TAP stream (after `./`), and the same outcomes and
    failure lines.

  The runner tests cover argv, a single record read, no read after a failed execution, and config refusals. The
  table test checks that a cpanfile project builds with the entry. The reader tests cover assertion lines, refusals,
  agreement with the line real 5.26.3 TAP reports, and every committed operator case's declared lines.
- **Docker, image-only.** `evals/case_e2e/operator_tests.py` drives the product's own `build`, `install`,
  `DockerRunners`, witness and `assess`, with operator-written tests and no model, on fresh offline containers of
  the Perl 5.26.3 image.

## Decisions and open questions

- `file_open` is the Perl recorder's only kind, matching Python. In the Docker runs, all three corpus Perl
  development topics needed no CPAN download and ran cleanly. Their tests told the revisions apart, but their effects
  have no recorder in any language: process start (cmdi), a credential check (adminpw) and a header string
  (responsesplitting). The gate therefore stays inconclusive. sqli has the same gap and was not run here because its
  setup needs CPAN. A process-start recorder needs its own spec: an in-process shell-versus-argv rule, shared with
  Python's audit events. It is the next bounded capability (PLAN-0088).
- **Tamper risk.** Test code could locally replace the override and restore it. There is no Perl authored-test
  admission check (Ruby and JavaScript have none either), so this risk stays tamper-evident only.
- **Not yet observed live.** Whether the local model plans `not_ok` and Perl subtests from the facility text is
  unknown until a live run.
