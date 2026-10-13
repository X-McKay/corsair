---
id: PLAN-0088
kind: plan
title: One complete Perl setup, execution and evidence path on the image-only route
status: in_progress
updated: 2026-10-13
related: [SPEC-0074, PLAN-0087, ISSUE-0008, SPEC-0061, SPEC-0073]
---

# One complete Perl setup, execution and evidence path on the image-only route

## Objective and dependencies

Lane 4 of [PLAN-0087](PLAN-0087-corpus-baseline-loop.md): make one non-Python language complete through setup,
execution and admitted evidence under plain Docker, generically, without recognising any case. Perl was chosen over
JavaScript for two reasons. Its image, TAP runner and environment admission were already on main, and its five
development topics are small `lib/*.pm` projects that run on core Test::More. JavaScript would also need dependency
capture for lockless projects and an effect recorder before reaching the same point. Design: [SPEC-0074](../specs/SPEC-0074-perl-product-route.md).

No dependency on ISSUE-0008: every request here is paired. Lane 2's `names_test_in` rule (PR #126, merged as
`bfc4e52`) is merged into this branch. Authoring now admits a Test::More `path.t#subtest` id that the rule ties to
its approved file, read by the TAP assertion reader added here. No second id-path check is added.

## Steps

- [x] Reproduce: corpus capture of `ih-perl-cmdi`, `ih-perl-sqli` and `ih-perl-xss` at main `1815f75`. `build()`
  selects `perl-5.26-make` / `tap-harness` and then refuses with `no harness entry for the tap-harness framework
  yet`, before setup or any model call.
- [x] Mechanism: the one framework table has no Perl entry. Behind it, three further generic gaps would stop any
  Perl run: no witness recorder, no failure type for a failed Test::More assertion (the gate reads it as
  `unclassified_failure`), and no Perl assertion reader in authoring (the final check parses `.t` files as Python).
- [x] Table entry `tap-harness`: cpanm setup from the project's manifests, `PERL5LIB` for installed dependencies,
  operator prefix `perl -Ilib`, witness record path.
- [x] Perl witness probe (`file_open`, same record and gate), shared record read-back in `NativeRunner`.
- [x] TAP failure type `not_ok`. `./` dropped from failure locations.
- [x] Authoring reader `perl.py` wired into `assertion_lines`. Authoring's input admits `path.t#subtest` ids, on main's
  `names_test_in` rule.
- [x] Docker proof through product ports with operator tests (`evals/case_e2e/operator_tests.py`, committed cases).
- [x] Compare frozen scripted evaluations against main.
- [x] RIG0 replay of all six committed cases, sqli with CPAN setup: all matched (below).
- [ ] Live: the same corpus topics through `corsair run` with the local model (RIG0), once lane ordering allows.
- [ ] Next capability: a process-start recorder (spec first), so cmdi-like topics can be decided.

## Validation and progress

Offline (cloud container, Docker 29.8.2, host Perl 5.38.2):

- `pytest -n 4 tests/unit tests/agents tests/configuration`: 1971 passed before the final tests landed. Re-run after
  all changes: see HANDOFF-0114.
- New: `tests/unit/test_perl_witness.py` 20 cases with the real probe in host Perl; TAP runner witness tests;
  `tests/agents/test_perl_assertions.py`; Perl request build in `tests/agents/test_case_e2e.py`.
- Scripted isolated evals, `make eval AGENT=<a>` on this branch and on a main `1815f75` worktree: authoring 20/20,
  assessment 54/54, planning 12/12, environment 16/16, identification 16/16 clean on both. Identities, assertions,
  per-case results and all efficiency means are identical; only `task_seconds` differs (±0.004 s). No frozen set
  holds a Perl case, so this shows no regression only, not Perl agent quality.

Docker, image-only, plain Docker in the cloud container:

- Image: local build of `deploy/qualification/toolchains/perl526`, config `sha256:329e659a4d80…`.
- Probe digest `7b220733ddf5…`.
- Every container ran offline with capabilities dropped. Setup used the default bridge and needed no download,
  because every requirement was core.
- Evidence archive: `/mnt/project-files/lane4-perl/perl-operator-cases-docker-20261013.tar.gz` (dependencies and
  repositories excluded).

| Case | Kind | Setup | Baseline (control / security) | Candidate | Witness | Gate | Matches expectation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| perl-notes | synthetic positive, cpanfile, 3-arg write | cpanm, nothing fetched | passed / failed `not_ok` line 16 | passed / passed | admitted both: observed; absent + `no_file_open` calibrated | completed / reproduced / verified | yes |
| perl-pages | synthetic transfer, Makefile.PL, 2-arg bareword read, exported alias, qualified symbol | cpanm configure, nothing fetched | passed / failed `not_ok` line 19 | passed / passed | admitted both | completed / reproduced / verified | yes |
| ih-perl-cmdi | corpus development | cpanfile (empty) | passed / failed `not_ok` | passed / passed | target entered; not admitted: control open not observed (process effect) | completed / inconclusive / not_verified | yes (expected gap) |
| ih-perl-adminpw | corpus development | cpanfile | passed / failed `not_ok` | passed / passed | same | completed / inconclusive / not_verified | yes (expected gap) |
| ih-perl-responsesplitting | corpus development | cpanfile | passed / failed `not_ok` | passed / passed | same | completed / inconclusive / not_verified | yes (expected gap) |
| ih-perl-sqli | corpus development | needs DBI, DBD::SQLite from CPAN | not run here | not run here | not run here | not run here | unrun in the cloud container (no registry route); run on RIG0, see below |
| ih-perl-xss | corpus development | Build.PL needs Module::Build and Test2::V0 from CPAN | not run | not run | not run | not run | unrun; Test2::V0 subtests are outside the lister and probe |
| the one held-out Perl topic | held out | n/a | n/a | n/a | n/a | n/a | never inspected or run |

Every workspace and container cleanup was confirmed. The operator tests and expectations are evaluation artifacts in
`evals/case_e2e/operator_cases/`. No production code reads them.

RIG0 replay (operator run relayed 2026-10-13 22:06Z; no model, run alongside another lane's model run). Worktree
`.worktrees/non-python-path` detached at `c8eba1d`. Image: a local RIG0 build of the same `perl526` source, config
`sha256:ce3853861371…`. Its digest differs from the cloud build `329e659a4d80…` because they are separate builds; both
are from the row's digest-pinned base. All six committed cases matched their expected gate:
- perl-notes and perl-pages: completed / reproduced / verified.
- ih-perl-cmdi, ih-perl-adminpw, ih-perl-responsesplitting and ih-perl-sqli: completed / inconclusive / not_verified,
  with limitations `witness_missing` x2, `no_valid_run` and `baseline_not_reproduced`.
- ih-perl-sqli: its setup reached CPAN over the Docker bridge and installed DBI into `.corsair-deps`.

Evidence is at `.runs/perl-operator-1` under that worktree. No matrix change follows. The row pins the base image,
and `CORSAIR_IMAGES` names the locally built image per host. Pinning one shared built image would need a published
image, which is an operator decision outside this lane.

Interpretation: setup, discovery, one execution, TAP admission, exit agreement, the witness record and the gate now
carry Perl end to end. The two synthetic cases show a decisive evidence-backed disposition is reachable. The corpus
topics show the binding gap for Perl development topics is effect coverage (process, query, header and credential
effects), not Perl plumbing; Python has the same gap. No agent-quality, accuracy or OpenShell claim is made.

## Decisions and next action

- **Simplicity and generality.** Every production change is keyed to the framework row or Perl's documented
  semantics: cpanm, `PERL5LIB`, Test::More's `subtest`, `CORE::GLOBAL::open`, TAP's `not ok`. Nothing names a case,
  repository, CWE or expected verdict. The only shared-code change is the record read moving to the runner base, now
  that it has its second consumer.
- **Transfer.** Transfer is shown by a second, structurally different synthetic project and by three distinct corpus
  topics reaching valid TAP admission and target-attributed records. That is not tuning: the operator tests and
  expectations were written after the code and do not change it.
- **Next bounded action (live, RIG0, coordinator relays).** First run the committed cases on RIG0's own perl526
  image, including `ih-perl-sqli`, which needs CPAN. Then run `corsair run` on `ih-perl-cmdi` and `ih-perl-adminpw`
  with the local model to see whether planning and authoring produce Perl subtests and `not_ok`. Expect INCONCLUSIVE
  for both. Exact commands are in HANDOFF-0114.
- **Next capability.** A process-start recorder spec for Perl and Python together (string and shell forms versus
  argv), so command-injection topics can be decided.
