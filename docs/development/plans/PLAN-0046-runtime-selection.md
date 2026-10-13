---
id: PLAN-0046
kind: plan
title: Runtime selection from project build files
status: complete
updated: 2026-10-13
related: [SPEC-0042, SPEC-0029, SPEC-0007, PLAN-0008, PLAN-0021, HANDOFF-0064]
---

# Runtime selection from project build files

## Objective and dependencies

Implement [SPEC-0042](../specs/SPEC-0042-runtime-selection.md) offline: detect each project's runtime, build tool and test framework requirement from its own build files; match it against an operator-owned matrix of qualified images; report the outcome over the benchmark cases. This is gap G15 and the offline half of step 5 in IDEA-0005 (on draft PR #39). The pinned commits come from the host acquisition in PR #42 (SPEC-0037, `benchmarks/source-pins.json`, not on main yet). No cluster is needed. This branch deliberately changes no file that #39, #41 or #42 change.

## Steps

- [x] Version sets and native range parsers (PEP 440, npm, RubyGems, Maven, Perl, Java naming) with a canonical text form.
- [x] Declarations, combination rule and shared CI reading; one detector per ecosystem (Python, Java, JavaScript, Ruby, Perl).
- [x] Typed requirement and selection contracts; operator matrix `deploy/runtime-matrix.yaml` with image and framework-runner rows; loader and matcher.
- [x] Unit checks per ecosystem and outcome; configuration guards tying rows to the prepared toolchain bases and existing evidence.
- [x] Report tool (`checkout`, `parents`, `report`) and a run over every acquired benchmark case.
- [x] Decided against building new image rows (JDK 8, CPython 3.7 or 3.10/3.11, Node 8, Ruby 3.1, Perl 5.26) in this plan. Each needs its own fixture project and toolchain gate run on a fresh node, which goes beyond a small hash-pinned edit to the current two-image preparation (`tests/qualification/prepare_toolchains.py` has one fixed control per language). They are the next plan.

## Validation and progress

Offline: `make test-config` passed 881 checks, which is main's 853 plus 26 runtime unit checks and 2 matrix guards.

Report run in the cloud container on 2026-10-13, against the pins file from PR #42's branch `claude/benchmark-repo-fetch-g6cnts` (head `4167369`):

```sh
PYTHONPATH=src:. .venv/bin/python -m evals.benchmark.runtimes checkout --trees $T --pins pins.json   # 1m40s, 72 revisions
PYTHONPATH=src:. .venv/bin/python -m evals.benchmark.runtimes parents --trees $T --pins pins.json --parents $P
PYTHONPATH=src:. .venv/bin/python -m evals.benchmark.runtimes report --trees $T --pins pins.json --parents $P --json benchmarks/runtime-requirements.json
```

Fetch coverage:
- `checkout` fetched build files for 39 of the 40 acquired cases, both revisions each.
- CVE-2023-31486 (salsa.debian.org) was refused by this container's egress proxy with CONNECT 403. It stays `not_fetched`, not guessed.
- `parents` fetched 11 parent POMs from Maven Central. `org.apache:apache:17` hit HTTP 429 once and was fetched on the next invocation.
- The two Jenkins parents (`org.jenkins-ci.plugins:plugin:2.15` and `org.jvnet.hudson.plugins:analysis-pom:1.63`) are not on Central, and repo.jenkins-ci.org is blocked here (CONNECT 403). VUL4J-51 and VUL4J-57 therefore stay undetermined in this run. RIG0's network can fetch them.

Outcome over the 50 inventory rows ([table](../../../benchmarks/runtime-requirements.md)):

| Outcome | Cases |
| --- | --- |
| supported on an existing image | 0 |
| unsupported (requirement fully named) | 35 |
| undetermined | 4: VUL4J-51 and VUL4J-57 (parent POM unreachable here), CVE-2019-10744 and GHSA-4rvg-955w-h68q (no test framework at all) |
| not fetched | 1: CVE-2023-31486 |
| not acquired (no fix commit, SPEC-0037) | 10 |

Baseline and fix revisions agreed in every fetched case.

No case runs on the two existing images:
- No Python case's CI tests 3.12; the newest tested version is 3.11.
- Every Vul4J case targets Java 1.5 to 1.8 without CI evidence of a newer JDK.

Suggested new runtime rows, chosen greedily over the unsupported cases:

| Row | Covers |
| --- | --- |
| JDK 8 + Maven | 8 Java cases |
| CPython 3.7 | 9 Python cases; 3.10 alone would cover 7 |
| Node 8 | 5 JavaScript cases |
| Perl 5.26 | 5 Perl cases |
| Ruby 3.1 | 4 Ruby cases |
| Ruby 2.4 | 2 Ruby cases |

Frameworks are an equal blocker:
- JUnit 4 is needed by 7 Java cases. JUnit 5 is needed by VUL4J-18 only, at 5.4.0, which SPEC-0039 measured as ignoring the dry run.
- Pytest older than 9 is pinned by 5 Python cases.
- JavaScript needs Jest, Mocha, AVA and tape; Ruby needs minitest and RSpec; Perl needs the TAP harness.

Spot checks against the files:
- VUL4J-42 resolves JDK 8 from plexus parent 3.3.1's compiler 1.5 plus its own enforcer (>=7).
- Werkzeug's CI matrix stops at 3.11; its `3.12-dev` entry is kept as unparsed.
- VUL4J-6 pins Maven 3.5.0 through its wrapper and tests JDK 7, 8 and 9 on Travis.

Limits: this is metadata, not admission (PLAN-0021). A suggested row satisfies a case's runtime declarations, not its dependency closure or tests.

## Decisions and next action

- Java strictness, framework sufficiency, missing-runtime handling and the per-version (not kitchen-sink) image choice are recorded in SPEC-0042, along with why no new agent is needed.
- Next: prepare and qualify a JDK 8 + Maven row with a JUnit 4 fixture, and a CPython row with a pytest range below 9, with one toolchain gate per row. Then wire the selected row into `EnvironmentInput.toolchains` as part of G12.
- Stop condition: a row without its own gate evidence is never added to the matrix.
