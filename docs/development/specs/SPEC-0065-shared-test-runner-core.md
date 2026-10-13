---
id: SPEC-0065
kind: spec
title: One test runner core across languages
status: draft
updated: 2026-10-13
related: [SPEC-0028, SPEC-0039, SPEC-0041, SPEC-0061, PLAN-0071]
---

# One test runner core across languages

## Goal and scope

Al (2026-10-13): "We should generalize and consolidate as much as possible across languages and frameworks", and on the decision card, "Merge, then refactor": the Perl (#77), Jest (#83) and Minitest (#84) runners merge as they are, then one behaviour-preserving refactor follows, using their real captured outputs as its tests. New frameworks (Mocha, AVA, RSpec) arrive afterwards as small drivers.

The runners for pytest, Maven Surefire, Perl TAP, Jest and Minitest repeated the same discovery, execution, storage, exit agreement, claims, absent-witness and configuration checks almost line for line. Only four things genuinely differ per framework: the id grammar, the listing command and its reader, the run command, and the report format.

Not in scope: changing any runner's commands, ids, refusals or outcomes; the environment agent's framework admission; witnesses.

## Boundaries and design

**Runner core** (`adapters/native_runner.py`). `NativeRunner` owns, for every framework:
- the fresh workspace and its release;
- receipt completeness and no retries;
- the exact-listing check (`_discover`): one listing run; it continues only with exit 0 and exactly the two ids, each once;
- report retention before admission (`_store_report`);
- the typed failure (`_failure`);
- exit agreement and the control and security claims (`_completed`): every runner passes through it, so none can skip the check; the default rule is exit 1 exactly when a test failed or errored, and TAP overrides `_exit_agrees` with Test::More's failed count or 255 for a died file;
- the absent-witness answer for frameworks without a probe (`_no_witness`);
- the operator-prefix rule (`exact_discovery`);
- the shared configuration checks (`check_command`, `check_root`, `check_bounds`).

A framework driver supplies:
- `_validate`: its id grammar and the one-file or one-class rule;
- a listing argv and a reader from listing stdout to ids;
- a run argv;
- its own short sequence of exit and report checks, which really differ, for example Maven's empty report and the TAP wrapper's exit 125;
- a call to its report reader.

pytest keeps its witness probe.

**Report admission** (`reports/admission.py`). Every reader shares:
- `ReportError`;
- the bounded UTF-8 envelope (`admit_text`);
- duplicate refusal (`record`);
- exactly one result per expected id, in order (`exactly`);
- `failed_count` for exit agreement.

`reports/junit.py` holds the one JUnit XML `testcase` reader (`testcases`). pytest's JUnit and Surefire's reports both use it, with their own name keys and stack-frame readers. TAP's reader keeps its stream-specific rules (todo, skip, plan, Test::More exit codes) and uses the shared envelope, duplicate and missing-id checks.

**Image-case harness** (`tests/qualification/image_case.py`). It owns:
- the image config id guard;
- the commit's own blobs (`commit_tree`);
- the offline, capability-dropped container standing in for the workspace and execution ports, with a per-run copy, an optional offline build, then the patch;
- cleanup confirmation, evidence and `run.json`.

Each language module keeps only its setup script (dependencies with network, no test body), its build, mounts, environment, runner and config. The Perl harness now runs the commit's blobs, like the Java one.

## Acceptance and validation

Behaviour is preserved:
- Every existing unit test passes unchanged: the runner, JUnit, Surefire, listing and TAP suites over real captures, plus the harness smoke tests.
- The fixed Perl programs are byte-identical.
- CVE-2023-31486 under Docker through the consolidated harness and runner gives the same outcomes at both revisions.

Jest moved onto the core after #83 merged: its capture suite (71 tests) passes unchanged and `node_image_case.py` uses the shared harness. Minitest moves when #84 is on main, on the same terms.

## Decisions and open questions

The checks after a run that really differ by framework stay in each driver: Maven's missing report, the TAP wrapper's exit 125 and each framework's allowed exit codes. A table of flags would hide them. A shared "exactly the planned ids" rule also catches a patch that brings a whole upstream test file: the CPython 3.7 sqlparse case listed 60 tests and stopped at discovery (fixed by #88).

Plan: [PLAN-0071](../plans/PLAN-0071-shared-test-runner-core.md).
