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
- [x] Hand-off to the environment agent (`nodes/runtime/environment.py`): the selected row as the only `EnvironmentInput.toolchains` entry, a `RuntimeStop` otherwise, and a ready-result check.
- [x] Closed the Jenkins parents: rerun on RIG0 with repo.jenkins-ci.org reachable, and here with the same POMs from the jenkinsci GitHub release tags.
- [x] Decided against building new image rows (JDK 8, CPython 3.7 or 3.10/3.11, Node 8, Ruby 3.1, Perl 5.26) in this plan. Each needs its own fixture project and toolchain gate run on a fresh node, which goes beyond a small hash-pinned edit to the current two-image preparation (`tests/qualification/prepare_toolchains.py` has one fixed control per language). They are the next plan.

## Validation and progress

Offline: `make test-config` passed 892 checks on the original base (853 plus 37 runtime unit checks, 4 of them for the hand-off, and 2 matrix guards), 999 after merging main at `c8f3964` (with #41, #45 and #46), 1004 after the review fixes (5 more checks), and 1024 after merging main at `8c29e16` (with #42).

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
- The two Jenkins parents (`org.jenkins-ci.plugins:plugin:2.15` and `org.jvnet.hudson.plugins:analysis-pom:1.63`) are not on Central, and repo.jenkins-ci.org is blocked here (CONNECT 403). VUL4J-51 and VUL4J-57 were therefore undetermined in this first run; the next paragraph closes them.

Jenkins parents, 2026-10-13:
- RIG0 (`/home/al/git/corsair/.runs/runtime-selection-20261013/`, branch head `eac99a2`, pins from `9e722a1`) ran `checkout`, `parents` and `report` with both remotes reachable. `parents` wrote 15 POMs, including `org.jenkins-ci.plugins:plugin:1.596.1` and `2.15`, `org.jenkins-ci:jenkins:1.34` and `org.jvnet.hudson.plugins:analysis-pom:1.63`. Outcomes: 37 unsupported, 3 undetermined, 10 not acquired.
- Here, the same four POMs were taken from the jenkinsci GitHub release tags (`plugin-pom` `plugin-2.15`, `analysis-pom-plugin` `analysis-pom-1.63`, `jenkins` `jenkins-1.596.1` `plugins/pom.xml`, `pom` `jenkins-1.34`), each checked to declare that coordinate. The rerun's VUL4J-51 and VUL4J-57 rows, evidence and suggestion counts match RIG0's. The committed report is this rerun.
- VUL4J-51: JDK 8 (target 1.7) and JUnit 4.11 from analysis-pom; VUL4J-57: JDK 8 (`1.${java.level}` in plugin 2.15) and JUnit 4.12. Both are now unsupported for the JDK 8 and JUnit 4 rows.
- CVE-2023-31486 fetched on RIG0 but stays undetermined: the pin is Debian's perl interpreter repository, whose root has `Configure` and `debian/` but no `Makefile.PL`, `Build.PL`, `cpanfile` or `dist.ini`, and `cpan/HTTP-Tiny/` has no build file. Another fetch will not change it; SPEC-0042 records the open question.

Outcome over the 50 inventory rows ([table](../../../benchmarks/runtime-requirements.md)):

| Outcome | Cases |
| --- | --- |
| supported on an existing image | 0 |
| unsupported (requirement fully named) | 37 |
| undetermined | 2: CVE-2019-10744 and GHSA-4rvg-955w-h68q (no test framework at all) |
| not fetched | 1: CVE-2023-31486 here; undetermined on RIG0 (above) |
| not acquired (no fix commit, SPEC-0037) | 10 |

Baseline and fix revisions agreed in every fetched case.

No case runs on the two existing images:
- No Python case's CI tests 3.12; the newest tested version is 3.11.
- Every Vul4J case targets Java 1.5 to 1.8 without CI evidence of a newer JDK.

Suggested new runtime rows, chosen greedily over the unsupported cases:

| Row | Covers |
| --- | --- |
| JDK 8 + Maven | 10 Java cases |
| CPython 3.7 | 9 Python cases; 3.10 alone would cover 7 |
| Node 8 | 5 JavaScript cases |
| Perl 5.26 | 5 Perl cases |
| Ruby 3.1 | 4 Ruby cases |
| Ruby 2.4 | 2 Ruby cases |

Frameworks are an equal blocker:
- JUnit 4 is needed by 9 Java cases. JUnit 5 is needed by VUL4J-18 only, at 5.4.0, which SPEC-0039 measured as ignoring the dry run.
- Pytest older than 9 is pinned by 5 Python cases.
- JavaScript needs Jest, Mocha, AVA and tape; Ruby needs minitest and RSpec; Perl needs the TAP harness.

Spot checks against the files:
- VUL4J-42 resolves JDK 8 from plexus parent 3.3.1's compiler 1.5 plus its own enforcer (>=7).
- Werkzeug's CI matrix stops at 3.11; its `3.12-dev` entry is kept as unparsed.
- VUL4J-6 pins Maven 3.5.0 through its wrapper and tests JDK 7, 8 and 9 on Travis.

Independent review (an Opus sub-agent, read-only) found 11 issues, all fixed with regression checks before the PR:
- `unresolved` inputs not making the selection undetermined;
- the toolchains plugin's own version read as a JDK;
- non-Java lines of `.tool-versions` read as a JDK;
- unbounded Maven property expansion;
- crashes on malformed YAML, TOML, META or overlong versions;
- Poetry `~=` parsed with npm semantics;
- compiler-level precedence (plugin configuration over the property default);
- non-atomic checkout;
- unvalidated parent coordinates used in URLs and file names;
- exclusive lower bounds in `preferred`;
- CI `18.x` and commented requirement lines.

The rerun changed one row: CVE-2020-15123's CI x-range now admits Node 12.

Al's GitHub review of `eac99a2` found three P2 issues, each reproduced and fixed with a check that fails on the old code:
- an unread hard constraint (`requires-python = ">=3.13rc1"` with a 3.12.15 pin) still selected CPython 3.12.15. Unread lines now keep their strength, and unread constraints or pins make the selection undetermined, while unread tested CI alternatives do not;
- `poetry.lock`'s first `[[package]]` `python-versions` was read as the project range. Both lockfiles are now parsed as TOML: `[metadata] python-versions` for Poetry, top-level `requires-python` for uv;
- a valid TOML Pipfile with `requires = "3.12"` raised `AttributeError`. Pipfile tables are type-checked and recorded as unparsed. A wider sweep of 10 build-file names per language against structurally wrong but valid TOML, JSON and YAML found no other crash.

The report rerun after these fixes changed no outcome; the JSON gains each unread line's strength. PR #42 has since merged; main's `benchmarks/source-pins.json` differs from the pins used here only in CVE-2023-31486's URL and note, a case this container cannot fetch, so the report stands.

Limits: this is metadata, not admission (PLAN-0021). A suggested row satisfies a case's runtime declarations, not its dependency closure or tests.

## Decisions and next action

- Java strictness, framework sufficiency, missing-runtime handling and the per-version (not kitchen-sink) image choice are recorded in SPEC-0042, along with why no new agent is needed.
- Next: prepare and qualify a JDK 8 + Maven row with a JUnit 4 fixture, and a CPython row with a pytest range below 9, with one toolchain gate per row. These run in the JDK 8 and CPython 3.7 threads against the stable `deploy/runtime-matrix.yaml` row schema. Then call `environment_input` from the chain and the durable workflow as part of G12.
- Stop condition: a row without its own gate evidence is never added to the matrix.
