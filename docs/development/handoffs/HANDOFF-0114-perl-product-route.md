---
id: HANDOFF-0114
kind: handoff
title: Perl TAP on the image-only product route
status: recorded
updated: 2026-10-13
related: [SPEC-0074, PLAN-0088, PLAN-0087, ISSUE-0008]
---

# Perl TAP on the image-only product route

## Verified state

- **Branch and base.** Branch `claude/non-python-path-bp9gj6`, from main `1815f75` (PR #125). It is lane 4 of
  PLAN-0087: one complete non-Python path. Resolve this document's commit from git.
- **Language and mechanism.** Perl was chosen. On main, `corsair run` refused every Perl request with
  `no harness entry for the tap-harness framework yet`. Behind that, three more generic gaps would have stopped it:
  no Perl witness recorder, no failure type for a failed Test::More assertion, and no Perl assertion reader in
  authoring.
- **Delivered** ([SPEC-0074](../specs/SPEC-0074-perl-product-route.md), [PLAN-0088](../plans/PLAN-0088-perl-product-route.md)):
  - the `tap-harness` table entry (cpanm setup, `PERL5LIB`, `perl -Ilib`);
  - the Perl `file_open` probe `nodes/witness_probe.pl`, writing the same record to the same gate;
  - the record read-back shared in `NativeRunner`;
  - TAP failure type `not_ok`;
  - the authoring reader `agents/test_authoring/perl.py`;
  - the model-free Docker driver `evals/case_e2e/operator_tests.py`, with committed operator cases.
- **Docker results.** Under plain Docker, two synthetic Perl projects reach completed / reproduced / verified, with
  the witness admitted on both revisions. Three corpus Perl development topics (cmdi, adminpw, responsesplitting) run
  cleanly and their tests tell the revisions apart. The gate stays inconclusive because their effects have no
  recorder in any language.
- **Not done.** No live model run, no OpenShell gate and no accuracy claim. Matrix rows are unchanged: the Perl rows
  stay `image-only`.

## Validation and blockers

- **Offline suite.** `pytest -n 4 tests/unit tests/agents tests/configuration` on the final tree passed. Counts are in
  the PR. This run includes the 20 real-probe tests in host Perl 5.38.2, the TAP runner witness tests, the reader
  tests and the Perl request build. `git diff --check` is clean.
- **Scripted isolated evals.** Authoring, assessment, planning, environment and identification each scored
  identically to a main `1815f75` worktree: same identities, assertions and cases, only wall time differing. No
  frozen set holds a Perl case.
- **Docker runs.** Recorded in PLAN-0088's table. Evidence is at
  `/mnt/project-files/lane4-perl/perl-operator-cases-docker-20261013.tar.gz`. Cleanup of every container and
  workspace was confirmed. The image was a local build of `perl526` (config `sha256:329e659a4d80…`) with probe digest
  `7b220733ddf5…`.
- **Unrun.**
  - `ih-perl-sqli`: needs CPAN, and this container gives setup containers no registry route. An attempt to forward
    the proxy into the bridge was refused by the session's permission policy and was not worked around.
  - `ih-perl-xss`: needs Build.PL with Module::Build and Test2::V0 from CPAN. Test2::V0 subtests are outside the
    lister and probe.
  - The one held-out Perl topic: never opened or run.
- **Inference.** None was run here; this session cannot reach the local endpoint.

## Decisions and next steps

- **Generality.** All production changes follow the framework row or Perl's documented semantics. No case, CWE,
  repository or verdict appears in production code. The operator tests and expectations are evaluation artifacts.
- **Next bounded action (RIG0, coordinator relays; one live-inference user at a time).** In a fresh worktree of this
  branch's pushed head:

  ```sh
  W=/home/al/git/corsair/.worktrees/non-python-path   # git worktree add may need Al's hand: Bash(git worktree add:*)
  git -C /home/al/git/corsair fetch origin claude/non-python-path-bp9gj6
  git -C /home/al/git/corsair worktree add --detach $W <pushed head>
  cd $W && uv sync --locked
  docker pull docker.io/library/perl@sha256:c7e412792cb4f1a5b9b7a632c01a02fb469c615e6745279b4ae1821d03105bc7
  docker build --network=none -t corsair-perl526-lane4 deploy/qualification/toolchains/perl526
  echo "{\"perl-5.26-make\": \"$(docker image inspect --format '{{.Id}}' corsair-perl526-lane4)\"}" > $W/.runs/images-perl.json
  # 1. No model: every committed case, sqli included (setup reaches CPAN over the Docker bridge).
  PYTHONPATH=src:. .venv/bin/python -m evals.case_e2e.operator_tests --case perl-notes --case perl-pages \
    --case ih-perl-cmdi --case ih-perl-adminpw --case ih-perl-responsesplitting --case ih-perl-sqli \
    --images $W/.runs/images-perl.json --evidence $W/.runs/perl-operator-1
  # 2. Live, one case at a time once the model is free: the corpus capture, then the product entry.
  PYTHONPATH=src:. .venv/bin/python -m evals.corpus.issues --root $W/.runs/perl-issues --case ih-perl-cmdi --case ih-perl-adminpw
  CORSAIR_IMAGES=$W/.runs/images-perl.json uv run --locked corsair run --issue-json $W/.runs/perl-issues/ih-perl-cmdi/issue.json \
    --local-root $W/.runs/perl-issues --provider-config /home/al/git/corsair/.runs/fixture-e2e-20261012/provider.json \
    --stage-profiles $W/evals/fixture_e2e/stage-profiles.json --evidence $W/.runs/investigations/ih-perl-cmdi-1
  ```

  Expected for step 1: every case matches its `expected` (sqli inconclusive once setup installs DBI and
  DBD::SQLite). Expected for step 2: INCONCLUSIVE. What it tests is whether the environment stage admits a Perl
  smoke baseline, and whether planning and authoring produce two Test::More subtests with `not_ok`. Record whether
  the model was shared.
- **Next capability.** A process-start recorder, specified once for Perl and Python: shell-string versus argv, with
  the subject a command the shell would start. With it, cmdi-like topics can be decided. Query, header and
  credential effects need separate designs and are not planned.
- **Blockers that do not stop this lane.** Lane 2's #126 owns the planning and authoring id-path rule. ISSUE-0008
  owns candidate-free runs.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then PLAN-0087, PLAN-0088, SPEC-0074 and this handoff. Inspect git and
source; verify the Perl table entry, probe and reader exist on your base. Use the Corsair development skill. Next
bounded action: run the committed operator cases (evals/case_e2e/operator_tests.py) on RIG0's own perl526 image,
including ih-perl-sqli, then one live `corsair run` of ih-perl-cmdi when the model is free; or draft the shared
process-start recorder spec for Perl and Python. Never key production code to a case; keep operator tests and
expectations evaluator-only; never run held-out topics. Run the offline suite and scripted evals, preserve evidence,
update PLAN-0088/CURRENT.md, and write a new handoff.
```
