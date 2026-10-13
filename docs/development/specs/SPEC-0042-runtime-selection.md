---
id: SPEC-0042
kind: spec
title: Runtime selection from project build files
status: draft
updated: 2026-10-13
related: [SPEC-0007, SPEC-0026, SPEC-0029, PLAN-0046, PLAN-0008, PLAN-0021]
---

# Runtime selection from project build files

## Goal and scope

Close the offline part of gap G15 in IDEA-0005 (draft PR #39): nothing read a case's own build files, so every real case was assumed to run on the one image per language (CPython 3.12, Temurin 17). Following Al's direction on 2026-10-13, the system must work for any language, version and runtime: versions come from the project's own build files and are matched against a tested set of sandbox images, with no per-case overrides and no single image per language. A project that needs an untested runtime is reported `unsupported` with that runtime named, and is never run on a different version.

This spec adds three things:

- a deterministic detector that turns build metadata into a typed runtime requirement;
- an operator-owned runtime matrix with a matcher;
- a report over the benchmark cases.

It also adds the hand-off from a selection to the environment agent's input. Excluded: building or qualifying new images, wiring that hand-off into the chain or durable workflow (G12), dependency installation (SPEC-0026), and test runners for frameworks other than pytest (G6). Execution needs no cluster, and nothing runs project code.

## Boundaries and design

**Detector** (`src/corsair/nodes/runtime/`).
- `is_build_file(path)` selects the build files from a snapshot listing. `detect(files, language, parents=)` reads only those bytes and returns a `RuntimeRequirement` (or a reason string when no single language applies).
- One module per ecosystem reads its formats as data:
  - Python: `pyproject.toml` (requires-python, classifiers, Poetry main, dev and group tables, extras, PEP 735 `dependency-groups`, `tool.uv` dev dependencies, build backend), root `*-requirements.txt`/`*_requirements.txt` files, `setup.cfg`, `setup.py` through `ast` (never executed), requirements files, `tox.ini` envlists, `Pipfile`/`Pipfile.lock`, `uv.lock` top-level `requires-python` and `poetry.lock` `[metadata]` (per-package ranges are never project constraints), `.python-version`, `runtime.txt`.
  - Java: Maven POMs with in-tree modules and supplied parent POMs. It reads properties, compiler release/target/source, enforcer `requireJavaVersion`/`requireMavenVersion`, the toolchains plugin, Surefire and JUnit 3/4/5 and TestNG dependencies. It also reads Gradle compatibility, toolchain and dependency lines, Maven and Gradle wrappers, `.java-version`/`.sdkmanrc`/`.tool-versions` and `Jenkinsfile` JDK declarations.
  - JavaScript: `package.json` engines, `packageManager`, the test script (following `npm run`) and dev dependencies; `.nvmrc`/`.node-version`; lockfile versions.
  - Ruby: gemspec `required_ruby_version` and dependencies (literal strings only), Gemfile `ruby`, `Gemfile.lock` RUBY VERSION, BUNDLED WITH and framework specs, `.ruby-version`.
  - Perl: `Makefile.PL`/`Build.PL` `use 5.x`/`MIN_PERL_VERSION`, `cpanfile`, META, `dist.ini`. A Perl build file implies the TAP harness.
- CI is shared across languages: GitHub workflow matrices and setup inputs (jobs whose name or `run` steps look like testing), Travis language keys and includes, and AppVeyor Node versions.
- YAML scalars keep their written form, so `3.10` is not read as `3.1`.
- POMs with any markup declaration are refused before parsing.
- Inputs are bounded: 1 MiB per file and 4,096 build files; tox envlists expand to at most 128 environments, and a combined version set too long for the contract is recorded as unread rather than widened.
- A requirement-bearing field that is present with the wrong type (`requires-python = 313`, a list where a table belongs) is recorded as unparsed against the component it would have declared, never treated as absent.

**Version sets** (`versions.py`) are finite unions of intervals over numeric versions. There are parsers for PEP 440, npm semver (also used for Poetry), RubyGems, Maven ranges, Perl decimal versions and Java's `1.x` naming, plus a canonical text form (`3.8.* || 3.9.*`, `>=5,<7`) that contracts store and the matcher parses back. Pre-release and non-numeric entries (`3.12-dev`, `pypy-3.9`, `lts/*`, `jruby`) are kept as `unparsed` with the reason, never guessed.

**Combination rule.** Each declaring line becomes a declaration with a strength: `constraint`, `tested` or `pinned`. Per component:
- Constraints intersect.
- Pins, when present, decide the version.
- Otherwise the strongest tested source present decides: CI, then tox, then classifiers, then a derived level.
- `allowed` is the result. An empty result is a conflict and makes the requirement undetermined.
- `preferred` is the newest explicitly named version inside `allowed`, falling back to its lower bound.

For Java, a compiler level T gives two declarations:
- a hard constraint: JDKs that can still compile T (javac drops `-source 5` at 9, 6 at 12 and 7 at 20);
- a derived tested version of JDK max(T, 8), so a 1.6/1.7/1.8 project without CI evidence runs on JDK 8, not on 17.

Maven inheritance follows nearest-wins for compiler level and Surefire. Test frameworks come from the root POM and its ancestors, falling back to the reactor modules as alternatives; POMs under `src/` are templates, not modules. A parent POM that is neither in the tree nor supplied is recorded in `unresolved`, never assumed.

**Components** carry a `provider`:
- `image` components must be provided by the sandbox image: the runtime, Maven/Gradle, npm/yarn/pnpm, Bundler, make.
- `registry` components come from the project's own dependencies during setup: the test framework, Surefire and the Python build backend.

Only test frameworks among registry components are matched, against runner support. Every component carries its evidence (path, line, excerpt, strength, source, declared set).

**Matrix** (`deploy/runtime-matrix.yaml`) is operator-owned, and nothing a project or agent supplies edits it.
- `images` rows name a digest-pinned base image, the image source, the exact runtime and tool versions, and qualification evidence (record ids and a report path). The loader refuses a row without these.
- `frameworks` rows name a framework family, the versions a Corsair runner and report parser are qualified for, the runner and its evidence. A required `images` list names the image ids the range was qualified on, so a new image row has no framework support until a range is qualified on it, and pytest 6 to 7 on CPython 3.7 and pytest 9 on CPython 3.12 are two rows. The loader refuses an empty list, two rows of one framework applying to the same image, or an `images` entry that is not a row of that language.
- Today the matrix holds the two qualified images (CPython 3.12.15; Temurin 17.0.20.1 with Maven 3.10.0) and one framework row (pytest 9.0.x). JUnit 5 is not listed yet: PR #41's Maven runner is now on main, and its row needs the JUnit versions that runner is qualified for.
- Configuration guards check that image rows are exactly the prepared toolchain bases and that every cited report, record and runner exists.
- To add a row: build from a digest-pinned upstream base with hash-pinned offline contents, pass the toolchain gate for that row on a fresh node, then add the row with that evidence.

**Selection** (`matrix.select`) returns a typed union:
- `supported` names the first row in which every runtime and image tool contains the required version and at least one declared test framework overlaps a qualified runner range. Setup must then pin the framework inside that overlap.
- `unsupported` lists the components no row provides, with their allowed sets and preferred versions, plus each rejected row's unmet checks.
- `undetermined` names what is missing: an undeclared runtime version, conflicting declarations, an unidentified test framework, unresolved inputs, or a constraint or pin the detector saw but could not read.

Each unread line keeps the strength it would have had. An unread constraint or pin on the runtime or an image tool makes the result undetermined, because it could exclude the row (`requires-python = ">=3.13rc1"` beside a 3.12 pin). An unread framework constraint cannot count as the qualified runner; if the runtime fits a row and no readable framework does, the result is undetermined. Unread `tested` entries, such as CI PyPy or dev jobs and a Jenkins `buildPlugin()` default, are alternatives and do not block.

There is no fallback row and no "close enough" version.

**One image per runtime version, not a kitchen-sink image** (Al's question, 2026-10-13):
- Each row is one runtime version on its upstream image. Qualification evidence stays per digest, and old runtimes keep the OS bases they need.
- A sandbox carries only the runtime its case uses.
- On RIG0, images in a family share layers and only rows that queued cases need are loaded.
- A row's `selector` field is reserved for a later hybrid (one image per language carrying several versions, chosen by `JAVA_HOME` or interpreter path). The loader refuses selectors until such an image is qualified, and the sandbox's observed runtime version would still be checked against the selection.

**No new agent** (Al's question, 2026-10-13). Runtime selection is deterministic: a parser and a set intersection. Over the 39 fetched benchmark cases, 37 resolve to a fully named requirement once the Jenkins parent POMs are supplied (PLAN-0046). The two undetermined cases have no framework at all: one package's test script exits with "no test specified", and the other runs a sanity script. Choosing a framework for those is a policy decision (an open question below), not model judgement over ambiguous files.

The consumer is the existing environment agent (SPEC-0029). The selected row becomes the only entry in `EnvironmentInput.toolchains`, and an `unsupported` or `undetermined` selection stops before the agent runs. The agent keeps its current job of proposing setup and test commands inside the selected image.

`nodes/runtime/environment.py` is that hand-off, deterministic and without SDK types:
- `environment_input` returns an `EnvironmentInput` whose only toolchain is the selected row, with the prepared image reference from the operator's image receipt (`prepared`, row id to `repository@sha256:...`).
- It returns a `RuntimeStop` with the reason instead when there is no requirement, the selection is `unsupported` or `undetermined`, or the selected row has no prepared image on this node.
- `check_ready` refuses a `ReadyEnvironment` that names another toolchain or image, or a framework the selection did not admit.

Calling it from the chain and the durable workflow is part of G12 and is not built here.

**Report** (`evals/benchmark/runtimes.py`):
- `checkout` makes a blobless shallow fetch of each pinned commit (from SPEC-0037's pins file) and writes only the blobs `is_build_file` selects.
- `parents` fetches the parent POMs those trees name from an operator-owned list of repositories (Maven Central, Jenkins public). A project's own `<repositories>` are never followed.
- `report` writes markdown and JSON with one row per inventory case, for the baseline candidate and the fix, plus a greedy suggestion of which runtime rows cover the most unsupported cases.

## Acceptance and validation

Offline checks:
- Version parsers and the canonical round trip.
- One fixture per ecosystem: CI outranking classifiers, YAML `3.10`, PyPy and dev entries kept unparsed, `setup.py` parsed without running, tox brace expansion, POM inheritance from a supplied parent, a missing parent left unresolved, markup declarations refused, JUnit 3 recognised, the JDK compile window, npm script indirection, lockfile npm range, gemspec/lock/CI for Ruby, Perl decimal versions.
- Language choice.
- Selection outcomes: supported, unsupported runtime, unsupported framework, conflict, framework overlap with an added runner row, refused selector, duplicate rows.
- Matrix guards against the prepared toolchain bases and existing evidence.

Validation is the report over the benchmark trees fetched in this container (PLAN-0046 records the commands and results). It is metadata only: no case is built, run or admitted, and an `unsupported` outcome says what a new matrix row needs, not that the case would pass with it.

Live qualification of any new row stays with the toolchain gate (SPEC-0007) on a fresh node.

## Decisions and open questions

Defaults chosen where the work forked:
- **Java strictness.** A Java project's compiler level selects that JDK (JDK 8 for 1.5 to 1.8) unless CI names others. The alternative, any JDK still able to compile the level, would admit most Vul4J cases on JDK 17, which is exactly the "different version" Al ruled out.
- **Frameworks.** One supported framework suffices among those a project declares.
- **Missing runtime.** No runtime declaration means undetermined, never the newest image.
- **Pins over tested sets.**

Open questions:
- Which framework to author with when a project has none (CVE-2019-10744, GHSA-4rvg-955w-h68q). Node's built-in test runner for the selected Node version is a candidate.
- Whether to accept a Maven/Gradle wrapper pin as satisfied by an image tool of the same major version (VUL4J-6 pins Maven 3.5.0).
- Runner qualification across framework versions (pytest older than 9, JUnit 4, TestNG, Jest, Mocha, minitest, RSpec, TAP). PR #41 starts JUnit 5.
- Parent POM fetching moving into the SPEC-0026 dependency phase.
- The requirement root for a module that ships inside its runtime. CVE-2023-31486 pins Debian's whole perl interpreter repository; HTTP::Tiny lives under `cpan/HTTP-Tiny/` without a build file of its own, so the case is undetermined. Either the case names that directory as its project root, or a perl core checkout is treated as building its own runtime. This is a case-definition decision, not a detector gap.

The plan is [PLAN-0046](../plans/PLAN-0046-runtime-selection.md).
