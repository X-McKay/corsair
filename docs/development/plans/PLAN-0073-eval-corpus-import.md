---
id: PLAN-0073
kind: plan
title: Paired eval-corpus import
status: in_progress
updated: 2026-10-13
related: [SPEC-0067, SPEC-0042, PLAN-0046, SPEC-0032, SPEC-0022, SPEC-0029]
---

# Paired eval-corpus import

## Objective and dependencies

Implement [SPEC-0067](../specs/SPEC-0067-eval-corpus-import.md) offline: copy the infosec-harness corpus, load it as Corsair cases with evaluator-only oracles and a frozen split, and regenerate the SPEC-0042 report over the benchmark and the corpus. Running the cases end to end is the follow-up below and waits on the open workstreams (chain hand-off, environment agent in the chain, matrix rows) and on Al's go.

## Steps

- [x] Copy `eval-corpus/` verbatim from `X-McKay/infosec-harness` `52aa2ac` to `benchmarks/corpus/infosec-harness/`, with `SOURCE.md` (commit, digest, evaluator-only files).
- [x] `evals/corpus/cases.py`: typed manifest, one case per topic, oracle, hygiene refusals, agent input, salted split, held-out manifest; `tests/unit/test_corpus_cases.py`.
- [x] Corpus section in `evals/benchmark/runtimes.py report`; regenerate `benchmarks/runtime-requirements.{md,json}` on main `164a556`, then again on `1c6d26a` after #92 (outcomes printed through #92's `_outcome`, so image-only selections show as such; held-out corpus rows in the JSON reduced to counts).
- [x] Records: this plan, SPEC-0067, CURRENT.md row.
- [x] Rerun after #73 and #94 (main `26c5316`): benchmark supported 9 (live: the nine CPython 3.7 cases), supported (image-only) 9, unsupported 20, undetermined 2, not acquired 10; corpus unchanged.
- [x] Rerun after the Node 8 and Ruby 3.1 rows (#98, #99) reached main: regenerated on main `7d04cf3`; benchmark supported (image-only) 9 → 15, unsupported 20 → 14; corpus section unchanged.
- [ ] End-to-end follow-ups, in order, after Al's decision on undeclared runtimes and missing tests (below).

## Validation and progress

2026-10-13, cloud container, branch `claude/eval-corpus-import-jcfaz1` from main `164a556`:
- `python -m evals.corpus.cases --tree-digest` gives the digest in `SOURCE.md`; the loader accepts all 42 topics with no label word in any agent-visible file.
- Benchmark trees: `runtimes.py checkout` fetched all 74 acquired revisions. `parents` fetched 11 POMs from Maven Central after HTTP 429 retries (three invocations); repo.jenkins-ci.org is refused by this container's proxy (CONNECT 403), so the same four Jenkins POMs as PLAN-0046 were taken from the jenkinsci GitHub release tags. 15 POMs in all, as on RIG0.
- Benchmark outcomes on main's three image rows: supported 3 (VUL4J-33, VUL4J-37 and VUL4J-57 on `temurin-8-maven`), unsupported 35, undetermined 2, not acquired 10. VUL4J-6 now needs only Maven 3.5.0 (its wrapper pin, the SPEC-0042 open question); JDK 9 is no longer asked for.
- After #92 (main `1c6d26a`, four image rows with `evidence`): benchmark supported (image-only) 9 (three VUL4J cases on `temurin-8-maven`, six Perl cases on `perl-5.26-make`), unsupported 29, undetermined 2, not acquired 10.
- Corpus outcomes: supported 1 (the JUnit 4 / Java 1.7 Java topic on `temurin-8-maven`), unsupported 4 (two Java topics need JUnit 5.10.2, outside the qualified `==5.14.4`; two Perl topics need Perl and `tap-harness` rows), undetermined 37 (35 declare no runtime version, three of them also run Node's built-in test runner; the two C topics have no detector).
- Corpus after #92: supported (image-only) 3 (the JUnit 4 Java topic and the two Perl topics that declare a version), unsupported 2 (JUnit 5.10.2), undetermined 37.
- Upstream check: `python -m evals.corpus.cases --compare <infosec-harness 52aa2ac>/eval-corpus` printed equal digests and `diff -r --exclude=SOURCE.md` printed nothing.
- `make test-config`: 1627 passed before the records were added; `tests/configuration` plus the corpus and runtime unit tests (290) passed again after.

Not run: no corpus case was built, executed or sent to a model.

## Decisions and next action

What a full run of a corpus case needs, beyond the open workstreams:
1. **Runtime.** 35 cases declare no runtime version. Upstream leaves it out on purpose. SPEC-0042 makes that undetermined. Decision for Al: an operator-owned default row per language for undeclared projects (recorded as assumed in the selection), or a declaration added identically to both variants of the copy.
2. **Baseline test.** No corpus project ships a test, and the environment agent (SPEC-0029) and planner (SPEC-0022) require one discovered, passing baseline test. Same decision: an operator-owned smoke test that imports the target module when a project has none, or a Corsair-authored neutral test identical in both variants (checked on both, label-free).
3. **Delivery.** Each variant is at most a few files, inside the qualified fixture arrival envelope (64 entries, 4 MiB) that `OpenShellTestWorkspace` (SPEC-0032) uses, so no general transfer is needed. Variants need capture as a `SourceSnapshot` (a host-side commit per variant with neutral metadata).
4. **Images and runners.** Python on CPython 3.12 with pytest 9 works once a runtime is chosen. Java needs a JUnit 5.10 range on `temurin-17-maven`. JavaScript needs a current Node image, Jest 29, Vitest and Node's built-in runner (Node 8 and Jest 24 do not fit). Perl needs the 5.26 and `tap-harness` rows, plus Test2::V0 from CPAN during setup for one topic. C needs a gcc image with AddressSanitizer and a make-test runner.
5. **Chain.** Runtime selection in the chain (#73), the environment agent in the chain, and a chain eval set over corpus cases (`make eval AGENT=chain SET=corpus`), development split first.

Next: rerun the report once the row PRs merge, then follow Al's decision.
