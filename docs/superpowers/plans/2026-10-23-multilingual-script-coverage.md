# Multilingual Script Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the same differential probe verify repository-local scripts, CLIs and Java main classes while attributing exact target-line coverage across child processes in all four runtimes.

**Architecture:** Each adapter supplies a primary command and a separately sanitized post-processing command. Coverage instrumentation is inherited by target children during the primary command, then removed while reports are merged and normalized into the existing common coverage shape.

**Tech Stack:** coverage.py 7.13, Node 22 V8 coverage, JaCoCo 0.8.14, Devel::Cover 1.44, pytest, Docker.

**Spec:** `docs/superpowers/specs/2026-10-23-multilingual-benchmark-and-improvement-loop-design.md`

## Global Constraints

- Implement after `2026-10-23-probe-verdict-contract.md`.
- Direct-call behavior must remain unchanged while child coverage is added.
- A decisive child-process result requires the exact reported target lines from the child that executed the target.
- Children inherit the same offline, read-only-source, capability, privilege and resource restrictions as the driver.
- A child timeout, launch failure, uncaught exception or missing coverage is nondecisive.
- Do not add a second sandbox abstraction or a separate script-probe schema.
- Post-processing commands must not instrument themselves or mutate the evidence they are reading.
- Run `make test-offline` for every task and the runtime-specific Docker tests for each adapter task.

## Review Focus

- A probe that clears coverage environment variables before spawning must become `INCONCLUSIVE`; pin this in each runtime's script integration test.
- Multiple child processes must merge coverage without allowing a same-basename file from another source path to satisfy the target; pin exact target path and line checks in Tasks 2–5.
- A post-processor crash must be evidence error rather than silently using a partial report; pin this in Task 1.
- Child output large enough to hit the sandbox output limit must remain `INFRA`; pin this in Task 6.
- Source paths containing brackets, spaces or repeated basenames must normalize to one target; extend the existing Node and Java path-identity tests in Tasks 3 and 4.

---

### Task 1: Separate execution and report post-processing environments

**Files:**
- Modify: `src/corsair/frameworks/base.py`
- Modify: `src/corsair/kernel.py`
- Modify: `tests/fakes.py`
- Modify: `tests/test_kernel.py`

**Interfaces:**
- Produces: `PostCommand(argv: tuple[str, ...], environment: Mapping[str, str])` and `Framework.post_command(role: str, target_file: str) -> PostCommand | None`.
- Consumes: existing `Framework.command`, `environment`, `result_paths` and `read` contracts.

- [ ] **Step 1: Write post-command failure and environment tests**

Assert the kernel runs post-processing after the primary command with its own environment, records the invocation, and returns `ERROR` evidence when post-processing exits nonzero, times out or exceeds output limits.

- [ ] **Step 2: Verify the tests fail**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_kernel.py -k post_command -v`

Expected: FAIL because `PostCommand` does not exist and post-command exit status is currently ignored.

- [ ] **Step 3: Implement `PostCommand` and kernel handling**

Replace `after_command()` with `post_command(role, target_file)`. Capture and append post-command output to the role artifact; classify any unsuccessful post-command as `ERROR` or `INFRA` before reading reports.

- [ ] **Step 4: Verify the unit tests pass**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_kernel.py tests/test_evidence.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/corsair/frameworks/base.py src/corsair/kernel.py tests/fakes.py tests/test_kernel.py
git commit -m "refactor: isolate coverage post-processing"
```

### Task 2: Aggregate Python subprocess coverage

**Files:**
- Modify: `src/corsair/frameworks/pytest_.py`
- Modify: `images/python/Dockerfile`
- Create: `cases/cs-0001-b/input.json`
- Create: `cases/cs-0001-b/oracle.json`
- Create: `cases/cs-0001-b/reference-submission.json`
- Create: `cases/cs-0001-b/vulnerable/cli_target.py`
- Create: `cases/cs-0001-b/fixed/cli_target.py`
- Modify: `tests/test_docker_pilot.py`

**Interfaces:**
- Consumes: `PostCommand` from Task 1 and role-relative v2 submissions.
- Produces: a coverage.py configuration using parallel data and subprocess patching, plus a post-command that combines data before JSON rendering.

- [ ] **Step 1: Add a Python CLI integration test**

The reference probe must invoke `python /work/cli_target.py <payload>` with inherited environment, parse its output and return the invariant. Assert all four role/revision runs reach the target line and the pair is positive/negative with fix `verified`.

- [ ] **Step 2: Add the missing-child-coverage variant**

Clear `COVERAGE_PROCESS_START` only in the spawned child. Assert the Boolean observations remain available but the case is `INCONCLUSIVE` because exact target coverage is absent.

- [ ] **Step 3: Verify both tests fail**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_docker_pilot.py -k python_script -v`

Expected: FAIL because only the pytest parent is currently covered.

- [ ] **Step 4: Implement subprocess coverage**

Write an adapter-owned coverage rc file with `parallel = true`, `patch = subprocess`, `source = /work` and a result-directory data file. Set `COVERAGE_PROCESS_START` for the primary command. Post-process with `coverage combine` and `coverage json` under an environment without `COVERAGE_PROCESS_START`.

- [ ] **Step 5: Verify Python direct and script cases**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_docker_pilot.py -k 'python and (script or path)' -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/corsair/frameworks/pytest_.py images/python cases/cs-0001-b tests/test_docker_pilot.py
git commit -m "feat: collect Python child-process coverage"
```

### Task 3: Aggregate raw V8 coverage from Node children

**Files:**
- Modify: `src/corsair/frameworks/node_test.py`
- Create: `cases/cs-0002-b/input.json`
- Create: `cases/cs-0002-b/oracle.json`
- Create: `cases/cs-0002-b/reference-submission.json`
- Create: `cases/cs-0002-b/vulnerable/cli-target.cjs`
- Create: `cases/cs-0002-b/fixed/cli-target.cjs`
- Modify: `tests/test_javascript.py`

**Interfaces:**
- Consumes: `PostCommand` from Task 1.
- Produces: adapter-owned `render-v8-coverage.cjs` that reads every raw file under `NODE_V8_COVERAGE` and emits `{files: {absolute_path: {executed_lines: [...]}}}`.

- [ ] **Step 1: Add Node child coverage tests**

Invoke `process.execPath` on the repository CLI with default inherited environment. Assert exact child target lines for all four runs, including a target filename containing brackets. Add a variant that replaces the child environment and loses `NODE_V8_COVERAGE`; it must be `INCONCLUSIVE`.

- [ ] **Step 2: Verify the tests fail**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_javascript.py -k script -v`

Expected: FAIL because built-in test coverage does not establish normalized descendant evidence.

- [ ] **Step 3: Implement the raw V8 renderer**

For every script URL under `/work`, map covered byte ranges with positive counts onto one-based source lines, union reports across processes, and preserve literal paths. Ignore `.corsair` driver files. Render after the primary test under an environment without `NODE_V8_COVERAGE`.

- [ ] **Step 4: Verify Node direct and script matrices**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_javascript.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/corsair/frameworks/node_test.py cases/cs-0002-b tests/test_javascript.py
git commit -m "feat: merge Node child-process coverage"
```

### Task 4: Inherit JaCoCo instrumentation in child JVMs

**Files:**
- Modify: `src/corsair/frameworks/javac_java.py`
- Create: `cases/cs-0003-b/input.json`
- Create: `cases/cs-0003-b/oracle.json`
- Create: `cases/cs-0003-b/reference-submission.json`
- Create: `cases/cs-0003-b/vulnerable/src/ScriptTarget.java`
- Create: `cases/cs-0003-b/fixed/src/ScriptTarget.java`
- Modify: `tests/test_java_perl.py`

**Interfaces:**
- Consumes: `PostCommand` from Task 1.
- Produces: primary `JAVA_TOOL_OPTIONS` with one append-enabled JaCoCo destination and a sanitized JaCoCo CLI report command.

- [ ] **Step 1: Add Java main-class coverage tests**

Compile the repository class into `.corsair-java/classes`; the probe launches a second JVM for `ScriptTarget`. Assert package/basename identity, exact target lines and four fresh role containers. Add duplicate-basename and cleared-`JAVA_TOOL_OPTIONS` variants.

- [ ] **Step 2: Verify the tests fail**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_java_perl.py -k java_script -v`

Expected: FAIL because only the driver JVM currently has the JaCoCo agent.

- [ ] **Step 3: Instrument descendant JVMs**

Move the JaCoCo agent setting to primary `JAVA_TOOL_OPTIONS` with `append=true,dumponexit=true`. Run the report CLI in the post-command with `JAVA_TOOL_OPTIONS` absent so report generation cannot change the evidence file.

- [ ] **Step 4: Verify Java direct and script cases**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_java_perl.py -k java -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/corsair/frameworks/javac_java.py cases/cs-0003-b tests/test_java_perl.py
git commit -m "feat: collect JaCoCo coverage from child JVMs"
```

### Task 5: Merge Devel::Cover data from child Perl interpreters

**Files:**
- Modify: `src/corsair/frameworks/perl_tap.py`
- Create: `cases/cs-0004-b/input.json`
- Create: `cases/cs-0004-b/oracle.json`
- Create: `cases/cs-0004-b/reference-submission.json`
- Create: `cases/cs-0004-b/vulnerable/bin/script-target.pl`
- Create: `cases/cs-0004-b/fixed/bin/script-target.pl`
- Modify: `tests/test_java_perl.py`

**Interfaces:**
- Consumes: `PostCommand` from Task 1.
- Produces: inherited `PERL5OPT`/`DEVEL_COVER_OPTIONS` for primary execution and a renderer environment without either variable.

- [ ] **Step 1: Add Perl script coverage tests**

The probe must launch the repository `.pl` with the current Perl interpreter and inherited environment. Assert exact child statement coverage and four role/revision results. Add a cleared-`PERL5OPT` variant and a system-core-module shadowing assertion.

- [ ] **Step 2: Verify the tests fail**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_java_perl.py -k perl_script -v`

Expected: FAIL because Devel::Cover currently instruments only the TAP driver.

- [ ] **Step 3: Implement inherited Devel::Cover configuration**

Set primary coverage options through environment variables so descendant Perl interpreters append to the same run database. Merge runs and render JSON in a post-command whose environment preserves `PERL5LIB` but removes coverage auto-start variables.

- [ ] **Step 4: Verify Perl direct and script cases**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_java_perl.py -k perl -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/corsair/frameworks/perl_tap.py cases/cs-0004-b tests/test_java_perl.py
git commit -m "feat: merge Perl child-process coverage"
```

### Task 6: Qualify script execution as a four-runtime capability

**Files:**
- Modify: `src/corsair/matrix.yaml`
- Modify: `src/corsair/agent-contracts.yaml`
- Modify: `src/corsair/skills/differential-probing/SKILL.md`
- Modify: `src/corsair/skills/python-pytest/SKILL.md`
- Modify: `src/corsair/skills/javascript-node-test/SKILL.md`
- Modify: `src/corsair/skills/java-javac/SKILL.md`
- Modify: `src/corsair/skills/perl-tap/SKILL.md`
- Modify: `README.md`
- Modify: `docs/design.md`
- Modify: `Makefile`
- Modify: `tests/test_sandbox_output.py`

**Interfaces:**
- Consumes: Tasks 2–5.
- Produces: advertised direct/script capability evidence for every runtime and a `SCRIPT_CASES` deterministic gate.

- [ ] **Step 1: Add the cross-runtime script gate**

Define `SCRIPT_CASES` as the four conformance script directories and add a Make target that verifies each reference submission. Add a sandbox test where child output exceeds the limit and assert `INFRA` plus cleanup confirmation.

- [ ] **Step 2: Update runtime and producer guidance**

Document inherited instrumentation, allowed observations, safe fixed-side rejection handling and the rule that child environment replacement loses decisive coverage.

- [ ] **Step 3: Run the complete native suite**

Run: `BUILDX_CONFIG=/tmp/corsair-buildx DOCKER_BUILD_FLAGS='--secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt' UV_CACHE_DIR=/tmp/corsair-uv-cache make test`

Run: `make verify-scripts`

Expected: both PASS; each runtime produces two source and two fixed role records with exact target coverage and no remaining containers.

- [ ] **Step 4: Commit**

```bash
git add src/corsair/matrix.yaml src/corsair/agent-contracts.yaml src/corsair/skills README.md docs/design.md Makefile tests/test_sandbox_output.py
git commit -m "docs: qualify script entrypoints across runtimes"
```
