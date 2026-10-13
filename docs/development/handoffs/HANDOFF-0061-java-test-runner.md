---
id: HANDOFF-0061
kind: handoff
title: Java test identity, Surefire reports and Maven runner
status: recorded
updated: 2026-10-13
related: [SPEC-0039, PLAN-0043, SPEC-0028, SPEC-0033]
---

# Java test identity, Surefire reports and Maven runner

## Verified state

Branch `claude/java-test-reports-fhco63` from main `334aa03`. Delivered under [SPEC-0039](../specs/SPEC-0039-java-test-runner.md) / [PLAN-0043](../plans/PLAN-0043-java-test-runner.md):

- `ports/test_runner.py`: `JavaTestId` (`[module/]package.Class#method`, module-aware, Maven source path); `reports/test_observations.py` admits `#` in claim ids.
- `reports/surefire.py`: one-class Surefire report parser with dry-run verification; `reports/junit.py` exposes the shared `admit_xml`.
- `adapters/native_runner.py`: orchestration moved out of the pytest runner unchanged; `adapters/pytest_runner.py` and the new `adapters/maven_runner.py` subclass it.
- Tests: `tests/unit/test_surefire.py`, `tests/unit/test_maven_runner.py`, nine real reports with provenance in `tests/unit/surefire/README.md`, and the sample project that produced three of them.

No agent, gate, workflow, image or policy changed. The test authoring agent and planner still accept pytest ids only (G8). The witness for Java is specified, not built; Java runs end at best `inconclusive`.

## Validation and blockers

`make test-config`: 918 passed. Host-only evidence (PLAN-0043): the runner through real Maven offline on a sample project, a two-module sample and JSPWiki at both commits. With JSPWiki's upstream JUnit 5.4.0 the dry run is ignored and discovery is refused; with JUnit 5.14.4 and Surefire 3.6.0 overridden on the command line the baseline control passes and the security test fails at line 63, and both pass on the fix. Not run: OpenShell, Temporal, toolchain image gates. Blocked for a sandbox Java run: G1/G3 storage and fetch-based workspace (SPEC-0036, PR #39), an admitted offline JSPWiki closure in a Java image (G4/G5), the kind cluster (owned by another thread).

## Decisions and next steps

Settled here: both tests in one class; discovery only by the JUnit Platform dry run; Maven console on stderr, report on stdout. Open for Al: admit the JSPWiki framework override (JUnit 5.14.4 and Surefire 3.6.0, the image's versions) or build an operator `Launcher.discover` helper; JDK for Java 8 era cases. Next: Java image with JSPWiki's closure, then `MavenRunner` in the SPEC-0032 workspace on a fresh node, then Java ids through planning and authoring.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then SPEC-0039, PLAN-0043, IDEA-0005 (PR #39 until merged) and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. Build a Java toolchain image carrying an admitted offline Maven closure for JSPWiki (hash-pinned like the existing image) and run MavenRunner inside the SPEC-0032 test workspace on a fresh node, three runs per revision. Stop if the dry run is not honoured in the image, the closure cannot be admitted offline, or G1/G3 workspace storage remains blocked; continue Java id support in planning and authoring meanwhile. Run make test-config and the relevant live gate, preserve evidence, update records/CURRENT.md, and write a new handoff.
```
