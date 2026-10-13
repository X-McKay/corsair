---
id: HANDOFF-0063
kind: handoff
title: Version-independent JUnit discovery
status: recorded
updated: 2026-10-13
related: [SPEC-0041, PLAN-0045, SPEC-0039, PLAN-0043]
---

# Version-independent JUnit discovery

## Verified state

Built on SPEC-0039 (PR #41, merged as `971ac82`), branch `claude/java-test-reports-fhco63` restarted from that main. Delivered under [SPEC-0041](../specs/SPEC-0041-version-independent-junit-discovery.md) / [PLAN-0045](../plans/PLAN-0045-version-independent-junit-discovery.md): Maven runner discovery now compiles with the project's own build and lists the two methods with an operator-pinned JUnit Platform console launcher, for JUnit 4 and any JUnit 5 version; `reports/junit_listing.py`; the dry-run path, its parser option and its three fixtures are removed; new fixtures are two real launcher listings and a JUnit 4 Surefire 2.22 report. No agent, gate, workflow, image or policy changed.

## Validation and blockers

`make test-config`: 933 passed (930 on main 971ac82, plus the goal-free Maven prefix fix from the Codex review: the operator prefix holds options only and the discovery command must equal it). Host-only runs through real Maven on unchanged POMs (JUnit 4.12, JUnit 5.14.4 single and two-module, JSPWiki JUnit 5.4.0 at both commits) gave the expected outcomes (PLAN-0045). Blocked for live use: the launcher jar (`junit-platform-console-standalone` 1.14.4) and `maven-dependency-plugin` 3.8.1 are not yet in the Java toolchain image; G1/G3 workspace storage.

## Decisions and next steps

Al's direction (2026-10-13): Corsair adapts to each case's language, framework and runtime versions rather than changing the project. Following it here: JUnit discovery is version-independent. Left to the benchmark readiness inventory (IDEA-0005), not started here: per-case JDK and Python images chosen from the case's build files (G4/G5), and witnesses per effect kind so CWE classes other than file access can reach reproduced/verified (G7). Next: hash-pinned launcher and dependency plugin in the Java image and re-qualification, then the runner in the SPEC-0032 workspace.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then SPEC-0041, SPEC-0039, PLAN-0045 and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. Add junit-platform-console-standalone 1.14.4 and maven-dependency-plugin 3.8.1 to the Java toolchain image with hash pins, re-run the toolchain gate, then run MavenRunner inside the SPEC-0032 test workspace on JSPWiki's unchanged POM. Stop if the image cannot be qualified or G1/G3 storage is still blocked. Run make test-config and the relevant live gate, preserve evidence, update records/CURRENT.md, and write a new handoff.
```
