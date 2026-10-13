---
id: IDEA-0005
kind: idea
title: Gaps before every benchmark case runs end to end
status: proposed
updated: 2026-10-13
related: [SPEC-0036, PLAN-0040, PLAN-0021, IDEA-0004, SPEC-0025, SPEC-0026, SPEC-0029, SPEC-0031, SPEC-0032, SPEC-0033, ISSUE-0006, ISSUE-0007]
---

# Gaps before every benchmark case runs end to end

## Problem and evidence

The user asked on 2026-10-13 to continue until Corsair can test all of its examples and benchmarks. Today the full chain (identification, planning, authoring, baseline/candidate execution in OpenShell, witness, assessment, gates) runs only on the SPEC-0018 Python pair through `evals/fixture_e2e` and `evals/fixture_chain`, over one hand-built `FixtureCase` (`evals/fixture_e2e/case.py`). Nothing in `src/`, `evals/` or `tests/` reads `benchmarks/candidate-cases.json` or `benchmarks/cases/`. All 50 candidate cases are unadmitted with zero executions (PLAN-0021). This survey (read-only, main `334aa03`) lists what blocks each case class, with source evidence, and an order to close it.

**Case classes** (`benchmarks/candidate-cases.json`, 10 each): Java/Vul4J (Maven, exact fix commits 10/10, dataset oracles), Python/Vul4Py (pytest, fix 10/10, no dataset license found), JavaScript/SecBench.js (npm/Jest, fix 8/10 of which three are pull-request commit URLs, two without repository), Perl/CPANSA (prove/TAP, fix 6/10, no dataset oracle), Ruby/Ruby Advisory DB (Bundler, fix 6/10, three without repository). Common to all: no issue or advisory text (only id, CWE, category); `vulnerable_reference` empty; every known repository is public on github.com; size recorded only for JSPWiki (1,723 files, 14.1 MB tree). JSPWiki (VUL4J-18) alone has pinned parent/fix captures and a frozen two-test draft, never compiled or run.

| Gap | Evidence | Blocks | Size | Live needed |
| --- | --- | --- | --- | --- |
| G1 Storage quota | HANDOFF-0052; SPEC-0025 | none since 2026-10-13: deferred as hardening; a pre-flight size and free-space budget (SPEC-0025) stands in, quota recorded unqualified | medium | yes; design in [SPEC-0036](../specs/SPEC-0036-workspace-storage-quota.md) |
| G2 Case to agent input | no loader; `IssueAnalysisInput` (`agents/issue_analysis/contracts.py`), `FixtureCase` (`composition/direct.py`); no neutral issue text or scope per case | all 50 | small code, per-case review | no |
| G2b Repository-scale source for agents | inline `source_files` ≤16 files / 64 KiB (`agents/source/contracts.py`), same caps in planning and authoring inputs; no list/search tool; no snapshot-to-agent mapping | every real case | medium–large | agent quality re-measured live |
| G2c Host acquisition | `GitSource` needs a complete local bare repository, ≤4,096 files / 64 MiB (`adapters/git_source.py`); nothing clones; pull-request and `.patch` fix links need normalising | all | small, plus per-case normalising | network only |
| G3 In-sandbox fetch | `nodes/source_fetch.py` unconnected; test workspace upload capped at 64 files / 4 MiB (`adapters/openshell_workspace.py`) | every real case | medium | yes; after G1 |
| G4 Dependency setup | inventories for Python/Java/JavaScript only (`nodes/dependency_inventory.py`); Ruby/Perl refused (`nodes/phase_policy.py`); Python wheels-only | all; Ruby/Perl need spec rows | medium per ecosystem | yes |
| G5 Toolchain images | Python 3.12/pytest and a synthetic Java 17 image only; workspace admission runs Python in the sandbox (`openshell_workspace.py`) | Java 8/11, Node, Ruby, Perl | small each | toolchain gate |
| G6 Runner, report, witness are pytest-only | `TEST_ID` is `*.py::name` (`ports/test_runner.py`); only `adapters/pytest_runner.py`; JUnit parser reads Python frames (`reports/junit.py`); witness needs `-m pytest` (`nodes/witness.py`) | Java, JS, Ruby, Perl | medium per framework | yes |
| G7 Witness observes file opens only | `open` audit event only (`nodes/witness_probe.py`); gates need a witness to call reproduced or verified (`core/disposition.py`) | about 40/50 by CWE (XXE, ReDoS, injection, SSRF, deserialization, XSS, SQL) | large, spec first | yes |
| G8 Authoring assumes Python | `ast.parse` in `agents/test_authoring/static.py`, required at finalisation | non-Python | small–medium | no |
| G9 Private-repository credential | placeholder unobserved (HANDOFF-0052) | none of the 50 (all public) | — | off critical path |
| G10 Corpus admission | PLAN-0021: 0/50 admitted; Ruby/Perl vulnerable pins unresolved | scoring of all 50 | large, human review | yes |
| G11 Benchmark runner and scorer | none; `evals/fixture_chain/evaluate.py` `ChainOracle` is the pattern; ground truth in `benchmarks/cases/<id>/` is prose only | all | small–medium | no |
| G12 Environment agent unconnected | `ReadyEnvironment` has no mapping to the chain's `EnvironmentEvidence`; identity declared, not observed (runtime selection now runs first in the chain and the declared image must be the selected row's, SPEC-0060) | all (operator evidence allowed for bring-up) | medium | yes |
| G13 Limits sized for the fixture | execution ≤300 s / 1 MiB (`ports/execution.py`); durable revision 10 min (`workflows/chain.py`); stage caps ≤24 calls (`composition/direct.py`) | larger builds | small edits, each re-qualified | yes |
| G14 Other | durable chain not yet run on OpenShell (HANDOFF-0055); ISSUE-0007 limits live-quality claims; Vul4Py/SecBench.js tests cannot be copied in without a license; prove emits TAP | various | — | — |
| G15 No automatic toolchain, runtime or framework resolution | one image per language (Python 3.12, Java 17); JUnit 5 only in the environment agent table (`agents/environment/frameworks.py`); Vul4J needs Java 8/11, older CPython likely; nothing reads a case's own build metadata to choose versions | every case whose versions differ from the single pinned image | large | yes, per runtime in the matrix |

## Proposal and limits

**Target (Al, 2026-10-13):** the system handles any language, CWE, version and runtime automatically, including multiple JUnit, Java and Python versions, without per-case overrides or one pinned image per language. Every step below is built to that target: toolchain and framework choices are derived from the case's own build files (Maven/Gradle POMs and wrappers, `pyproject.toml`/`setup.cfg`/requirements/poetry metadata, `package.json` engines, gemspecs/Gemfile, cpanfile), resolved against an operator-owned, qualified runtime matrix of sandbox images, and recorded as observed environment evidence. A case whose requirement falls outside the qualified matrix is reported `unsupported` with the missing runtime named, never run on a substitute. Per-language and per-framework code exists only where formats genuinely differ (report parsing, test identity), behind one table per framework family.

Recommended order, each step measurable across all 50 cases once step 1 exists:

1. **Case manifests, loader and denominator report (G2, G11)**, offline: `benchmarks/cases/<id>/case.yaml` split into an agent-visible part (neutral issue, scope, repository, baseline and candidate commits) and an evaluator-only part (dataset id, CWE, fix reference, reference-test digest, `ChainOracle`-shaped expectations, split, admission status and blocking layer); `evals/benchmark/` joins all 50 inventory rows with manifests, refuses issue text naming the advisory or dataset, and reports attempted/blocked/unsupported counts by language, build system, CWE and blocking gap. First manifest: JSPWiki.
2. **Host acquisition (G2c)**: a bounded bare-repository fetch of exact commits over HTTPS from github.com, `fsck --strict`, then `GitSource` capture for every resolvable case, recording sizes and which exceed the capture ceilings.
3. **Repository-scale source access (G2b)**: a store-backed reader with bounded list and search tools replacing the 16-file inline inventory in all four agent stages; existing evals must not regress.
4. **Fetch-based test workspace (G3)** per SPEC-0025 with the pre-flight workspace budget, qualified on JSPWiki and one Python case. The SPEC-0036 quota (G1) was deferred by the owner on 2026-10-13 and returns before concurrent sandboxes or hostile workloads; step 5 no longer waits for it.
5. **Toolchain resolution and runtime matrix (G15, G5)**: read build metadata into a typed requirement (language, runtime version range, build tool, test framework and version), choose from a qualified image matrix (several Java, Python and Node versions first), and feed the environment agent and `EnvironmentEvidence`; JUnit 4/5 and pytest versions are framework-table entries, not new code paths. Ownership (answered 2026-10-13): no new agent. A deterministic requirement node parses build metadata and matches it to the image matrix (or returns `unsupported` naming the missing runtime); the existing SPEC-0029 environment agent takes that requirement as input and chooses only among matching images, keeping model judgement for test commands, CI steps and setup failures; framework versions extend `agents/environment/frameworks.py`; the observed environment reaches the chain through G12.
6. **Java runner (G6, G8)**: framework-specific test identity (the environment agent's `junit5` table is the second consumer), Surefire report parsing and Java assertion lines, then the frozen JSPWiki draft as the first real E2E-2 with operator-supplied environment evidence.
7. **Python and Java setup (G4)**, then the environment agent (G12), limit re-qualification (G13) and a durable rerun (G14).
8. **Witness for other effect kinds (G7)**, spec first, per CWE family.
9. **JavaScript, then Ruby and Perl**: matrix entries, SPEC-0026 inventory rows and runners (Jest JUnit reporter, minitest/rspec JUnit, TAP).
10. **Case admission (G10)** runs in parallel throughout: neutral issues, reference oracles and three runs per variant, with human review.

Limits: until G7 lands, most cases can at best end `inconclusive`/`not_verified` by design, which the report must count as such rather than as failures. Licensing (G14) restricts which dataset tests may be copied; reviewed equivalents are needed for Vul4Py and SecBench.js.

## Decision

Proposed. Steps 1 and the SPEC-0036 storage work start under [PLAN-0040](../plans/PLAN-0040-workspace-storage-quota.md) because neither depends on the other or on the kind cluster for offline parts; steps 2, 3, 6 and the offline part of 5 (build-metadata parsing into a typed requirement) are independent follow-ups suitable for parallel threads.
