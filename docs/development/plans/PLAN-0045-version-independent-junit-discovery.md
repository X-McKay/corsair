---
id: PLAN-0045
kind: plan
title: Version-independent JUnit discovery
status: complete
updated: 2026-10-13
related: [SPEC-0041, SPEC-0039, PLAN-0043, HANDOFF-0063]
---

# Version-independent JUnit discovery

## Objective and dependencies

Implement [SPEC-0041](../specs/SPEC-0041-version-independent-junit-discovery.md) on top of SPEC-0039 (PR #41). Offline and host only; the image change and sandbox run depend on the Java toolchain image work (G5) and the workspace storage work (G1/G3).

## Steps

- [x] Check the console launcher's `discover` on JSPWiki's JUnit 5.4.0 classes and a JUnit 4.12 project: both list exactly the selected methods and run no body; a missing method is silently absent, so the count check is required.
- [x] `reports/junit_listing.py`; Maven runner discovery replaced; dry-run code and fixtures removed.
- [x] Offline tests over captured listings and reports; host runs through real Maven on unchanged POMs.
- [x] Records, `CURRENT.md`, handoff.

## Validation and progress

2026-10-13, cloud development container, OpenJDK 21.0.12, Maven 3.9.11, launcher 1.14.4, dependency plugin 3.8.1, all Maven runs offline after the closures were fetched. Through `MavenRunner` with a local subprocess executor (scratch, not committed): JUnit 5.14.4 sample (root and two-module) discovered, control passed, security failed at line 21; JUnit 4.12/Surefire 2.22.0 sample discovered, control passed, security failed at line 8; JSPWiki on its own POM (JUnit 5.4.0, Surefire 2.22.0, no overrides) discovered at both commits, baseline control passed and security failed at line 63, candidate both passed; an id for a missing JUnit 4 method was a `collection_error` with nothing executed. `make test-config`: 930 passed (on main 971ac82). Codex review on PR #46 found that discovery reused the admitted discovery command as the Maven prefix, so a goal-bearing command (for example one ending in `test`) would run test bodies before the listing; the prefix is now operator-owned and goal-free (validated in the config), the runner refuses a discovery command that differs from it, and execution appends `test` itself. New tests cover both refusals; 933 passed.

Unrun: the toolchain image gate (the launcher is not yet in the image), OpenShell, Temporal.

## Decisions and next action

The JSPWiki version override from SPEC-0039 is no longer needed. Next: add the launcher jar and dependency plugin to the Java image with hash pins and re-qualify it, then run in the SPEC-0032 workspace.
