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

Offline: `make test-config` passed 892 checks on the original base (853 plus 37 runtime unit checks, 4 of them for the hand-off, and 2 matrix guards), 999 after merging main at `c8f3964` (with #41, #45 and #46), 1004 after the review fixes (5 more checks), 1024 after merging main at `8c29e16` (with #42), 1036 after merging `6be1b5f` (with #47), 1084 after merging `42a7273` (with #39), 1085 with image-scoped framework rows, 1088 after the second review's first three fixes, 1093 after merging `f6a87d6` (#58), 1100 after the remaining seven threads, 1174 after merging `8606068` (#57), 1179 after the include-group fix and the Poetry source nit, and 1227 after merging `9a6f78c` (#52, #54, #59).

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
| unsupported (requirement fully named) | 38 |
| undetermined | 2: CVE-2019-10744 and GHSA-4rvg-955w-h68q (no test framework at all) |
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
| Perl 5.26 | 6 Perl cases |
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

Al's re-review of `dbbb980` found three more bounded parser cases, each reproduced and fixed with a check through `detect`/`select` that fails on the old code:
- Pipfile `python_version` hid `python_full_version`; both are now pins, so `3.12` plus `3.12.14` allows only 3.12.14 and a `.python-version` of 3.12.15 conflicts;
- a present but non-string `requires-python` (`313`) was silently dropped and selection reported supported;
- a non-object `dependencies` in package.json raised `TypeError`.

The root cause was one pattern: `isinstance` guards that treated a present value of the wrong type as absent. A shared `typed()` accessor now records such a value as unparsed against the component it would have declared (runtime, image tool or framework). It is applied to every requirement-bearing field in pyproject, Pipfile, Pipfile.lock, Poetry/uv locks, package.json and Perl META; CI shapes stay tested alternatives. A non-string framework version in package.json is now unread instead of "any version", and Poetry/Pipfile table forms (`pytest = {version = "^9.0"}`) are read. A seeded sweep of 52,000 wrong-shape TOML/JSON/YAML documents through `detect` and `select` found one further crash (an `undetermined` reason over the 240-character contract limit), now truncated; a 300-document version of that sweep is a unit check. The report did not change.

The same re-review (posted from Al's account) added seven threads, all fixed with checks that fail on the old code:
- framework `images` is required, and the pytest row is scoped to `cpython-3.12-pytest`, so a new image row gets no framework support by default (blocking);
- pytest constraints in Poetry groups, PEP 735 `dependency-groups`, `tool.uv` dev dependencies and root `test-requirements.txt`-style files are read (blocking). Re-fetching the benchmark trees added three such files (CVE-2022-24065, CVE-2022-24439) and changed no outcome;
- an unreadable or undefined toolchains JDK pin is recorded as an unread pin (blocking);
- tox envlist expansion is capped before materialising, and an oversized combined set becomes an unread constraint;
- jenv names (`openjdk64-17.0.2`) no longer read the `64` as the release, and `system` is an unread pin;
- one unresolved version among a framework family's dependencies makes that family unread;
- SPEC-0042's benchmark counts and the CURRENT.md row now match the report and say the hand-off is not yet called.
The package.json `dependencies` thread repeated the earlier finding fixed in `20d34b6`.

Al's re-review of `f61e948` confirmed those fixes and found one more: a PEP 735 `include-group` whose value is a list or table raised `TypeError` (unhashable) during the group-membership test instead of recording an unread entry. The value must now be a string naming an existing group; anything else is an unparsed pytest constraint, so selection is undetermined. Four parametrised checks (list, table, number, unknown name) cover it, two of which fail on the old code, and the malformed-metadata sweep now generates `dependency-groups`/`include-group` keys.
The same review's nit is also taken: a Poetry `pytest = {git = ...}` (or path/url) entry with no `version` is an unread pytest constraint rather than any version. The report rerun over the stored trees gives identical results; only the detector digest in `inputs` changed.

From the same review's non-blocking notes: the report JSON now carries an `inputs` header with SHA-256 digests of the detector source, the matrix, the pins file, the inventory and each supplied parent POM, so a rerun (for example on RIG0) can be compared input by input; results are unchanged. Not changed: requirement lines with environment markers (`pytest<5; python_version<"3"` beside `pytest>=8; python_version>="3"`) still intersect into a conflict and give undetermined. That fails closed; evaluating markers against each candidate row is left for when a benchmark case needs it (none of the 39 does).

The CPython 3.7 image thread pointed out that per-language framework rows would let a 3.7 image claim pytest 9 (qualified only on 3.12) and the reverse. Framework rows took an `images` scope, with a selection check over two scoped pytest rows and loader refusals for overlap and foreign image ids; both toolchain threads were told by cross-session message.

The report rerun after these fixes changed no outcome; the JSON gains each unread line's strength. PR #42 has since merged; main's `benchmarks/source-pins.json` differs from the pins used here only in CVE-2023-31486's URL and note, a case this container cannot fetch, so the report stands.

Limits: this is metadata, not admission (PLAN-0021). A suggested row satisfies a case's runtime declarations, not its dependency closure or tests.

## Follow-up after merge (#48 merged as `a9ba2b0`)

- CVE-2023-31486: Al first chose `cpan/HTTP-Tiny` inside Debian's perl repository as the project root, but that directory has no build file there (RIG0's fetch), so he then chose (decision card, 11:10Z) to point the case at the upstream repository, which is also the inventory's `repository_url`. The fix reference is now Perl-Toolchain-Gang/HTTP-Tiny `77f557e` ("Change verify_SSL default to 1", released in 0.083; single parent `7bdf71f`), acquired here with `evals.benchmark.sources fetch` under the #42 rules (canonical GitHub URL, no redirects; 119 files, one symlink skipped). The report now reads `Makefile.PL`, `dist.ini` and `.travis.yml`: unsupported on the existing images, needing perl in 5.8 to 5.26 (CI-tested up to 5.26), make and the TAP harness, so the suggested Perl 5.26 row covers 6 cases. No project-root field was needed, so none was added.
- Codex's review of `028d724` (completed after the merge) found three P2s, each fixed with a check that fails on the old code: a PEP 508 direct reference (`pytest @ git+...`) is an unread pytest constraint instead of vanishing; every unresolved reason is cut to the 240-character contract limit; and an explicit `python` language accepts requirement-only trees (`requirements-dev.txt`, `requirements/*.txt`, `pytest.ini`, `.python-version`, lockfiles are Python markers).
- The report rerun over the stored trees changed no other case; the detector, inventory and pins digests changed.
- Codex's review of `7b42d2e` (#61): `requirements/test/dev.txt` was selected as a build file but only one level under `requirements/` was parsed, so a nested `pytest<8` vanished. Every selected file under `requirements/` is now read, at any depth; `test_nested_requirements_files_are_read` fails on the old code. Report results unchanged.
- Al's review of `7b42d2e` noted a pre-existing gap for the next detector slice: `[project] dependencies` is not read, so `pytest<8` there plus `[tool.pytest]` selects the pytest 9 image.
- `make test-config`: 1236 passed on main `0ad9900` plus this follow-up.

## Project dependencies (after #61, merged as `a459ced`)

Al's review of #61 found that PEP 621 `[project] dependencies` was never read, so `dependencies = ["pytest<8"]` with `[tool.pytest.ini_options]` selected the pytest 9 image. Those entries now go through the same requirement parser as extras, so a versioned pin, a direct reference and an unparseable spec behave as elsewhere; a non-string entry or a non-list value is unread and gives undetermined. `setup.cfg` `[options] install_requires` had the same gap and is read the same way (`setup.py` already read any requirement string). `test_project_dependencies_are_read` (seven inputs; the five defect cases fail on the old code, the two controls pass on both) and `test_setup_cfg_install_requires_is_read` cover it. The report rerun gives identical results; only the detector digest changed. The seeded 52,000-document sweep raised nothing. `make test-config`: 1246 passed on main `a459ced` plus this change.

## Decisions and next action

- Java strictness, framework sufficiency, missing-runtime handling and the per-version (not kitchen-sink) image choice are recorded in SPEC-0042, along with why no new agent is needed.
- Next: prepare and qualify a JDK 8 + Maven row with a JUnit 4 fixture, and a CPython row with a pytest range below 9, with one toolchain gate per row. These run in the JDK 8 and CPython 3.7 threads against the stable `deploy/runtime-matrix.yaml` row schema. Then call `environment_input` from the chain and the durable workflow as part of G12.
- Stop condition: a row without its own gate evidence is never added to the matrix.
