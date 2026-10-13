---
id: SPEC-0067
kind: spec
title: Paired eval-corpus import
status: draft
updated: 2026-10-13
related: [SPEC-0042, SPEC-0037, SPEC-0035, SPEC-0031, SPEC-0023, IDEA-0005, PLAN-0073]
---

# Paired eval-corpus import

## Goal and scope

Al asked (2026-10-13 14:26Z) to copy in the eval corpus from `X-McKay/infosec-harness` and drive towards a full end-to-end run for its use-cases. This spec covers the offline import: the corpus copied into the repository, a loader that turns it into Corsair cases with evaluator-only oracles and a frozen held-out split, and the SPEC-0042 runtime report regenerated to cover the new cases. Excluded: running any case, wiring the cases into the chain or `make eval`, new images or runners, and the Vul4J harvest the corpus carries under `external/`.

The corpus has 82 upstream cases in 42 topic directories (Python 22, JavaScript 9, Perl 6, Java 3, C 2). Each paired topic has two variant directories `a` and `b` of a small project, one exploitable and one not; two topics are unpaired. `manifest.json` holds each case's finding (title, description, file, line, symbol, CWE) and truth (expected verdict, reachability, sink). `verification/` holds tests asserting each variant's behaviour for 13 topics. The README holds the answer key. Fixtures ship no tests.

## Boundaries and design

**Copy.** `benchmarks/corpus/infosec-harness/` is a verbatim copy of `eval-corpus/` at upstream commit `52aa2ac`. `SOURCE.md` records the commit and a digest over every copied file. A unit test fails when the copy drifts from that digest, so a change is made upstream and copied again rather than edited here. The Vul4J attribution (CC-BY-4.0) is kept as upstream ships it.

**One case per topic** (`evals/corpus/cases.py`). The upstream case is one variant judged alone, with a verdict `potentially_exploitable` or `likely_not_exploitable`. Corsair's gate judges a baseline and a candidate revision with a benign control and a security test, so a pair maps onto the existing fixture-chain shape (SPEC-0035):
- A paired topic: the exploitable variant is the baseline revision and the other the candidate. The hypothesised oracle is completed / reproduced / verified (`ChainOracle`).
- An unpaired topic: only a baseline, expected at completed / not_reproduced / not_applicable. Corsair cannot refute a claim by testing, so `not_reproduced` is the strongest expected outcome and `inconclusive` is not a correct negative.
- Every oracle is a hypothesis until a chain run observes it, as in the benchmark manifests.

The reverse mapping (candidate first) and both-same mappings from SPEC-0035 are possible later and are not generated now.

**Agent-visible inputs.** `agent_input()` gives identification an `IssueAnalysisInput`: issue text composed from the finding fields upstream submits (title, reported file, line and symbol, CWE, description, component scope) and the baseline variant's non-empty files, under the neutral case id `ih-<language>-<topic>`. Variant directory names, verdicts, reachability, the manifest, the README and the verification tests are evaluator-only. The loader ports the upstream hygiene rule and refuses verdict words in finding text, variant paths and variant contents, a pair whose findings differ beyond location, a pair without one verdict of each kind, and symlinks in a variant.

**Held-out split.** Per language, the quarter (rounded down) of cases with the lowest salted SHA-256 of the case id is held out: eight cases, none in Java or C. `evals/corpus/held_out.json` maps each held-out id to the SHA-256 of its finding, oracle and both trees, and is rewritten only by `--freeze-held-out`. Held-out ids are never named under `docs/development/` or in the committed runtime report; tests enforce both.

**Runtime report.** `evals/benchmark/runtimes.py report` adds a corpus section: both variants of every case are read in place (no fetch) and run through the unchanged detector and matrix. The JSON adds `corpus` (held-out ids withheld) and the manifest digest under `inputs`. A language with no detector (C) is reported undetermined with that reason.

**Vul4J harvest.** `external/vul4j.json` holds 58 Vul4J pairs at remote commits with proof-test metadata, nine already in the benchmark inventory. It is copied as data only. Using it needs SPEC-0037 acquisition of each commit and removal of the upstream proof test from agent-visible trees, so it is not loaded as cases here.

## Acceptance and validation

Offline, in `make test-config`:
- 42 cases, 40 with a candidate, baselines all exploitable variants; oracles as above.
- Agent input carries the finding file and no verdict, variant path or manifest field.
- The copy matches its digest; an added verdict word, a diverging pair and a symlink are refused.
- The split is a quarter per language and matches `held_out.json`; no held-out id appears under `docs/development/` or in the runtime report.
- The committed runtime report covers every corpus case.

The report is build metadata, not execution: no case is built or run, and an `undetermined` outcome says what selection lacks, not that the case would pass with it.

## Decisions and open questions

Defaults chosen:
- One case per topic with the exploitable variant as baseline, matching the fixture chain's main case.
- Upstream verification tests are kept as evaluator-only reference oracles, never planted in a variant.
- The split is fixed now so no agent version is tuned on held-out cases.

Open, recorded in PLAN-0073:
- 37 of 42 cases are undetermined because their build files declare no runtime version, and SPEC-0042 refuses to guess one. Upstream omits the declaration on purpose (deriving the build is what its agents are measured on). Either selection gains an operator-owned default row per language for undeclared projects, or the corpus copy gains a declaration identical in both variants.
- Corpus projects ship no tests, while the planner requires a discovered baseline test (SPEC-0022).
- Runners and rows needed: JUnit 5.10, Node's built-in runner, Vitest, Test2::V0 under `prove`, and a C toolchain with AddressSanitizer.
