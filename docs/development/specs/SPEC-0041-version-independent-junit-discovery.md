---
id: SPEC-0041
kind: spec
title: Version-independent JUnit discovery
status: draft
updated: 2026-10-13
related: [SPEC-0039, PLAN-0045, SPEC-0028, SPEC-0007]
---

# Version-independent JUnit discovery

## Goal and scope

On 2026-10-13 Al asked that Corsair handle cases whatever their JUnit, Java or Python version, rather than adapting projects to Corsair. SPEC-0039's Maven discovery used the JUnit Platform dry run, which needs Platform 1.13 or later; JSPWiki pins JUnit 5.4.0, which ignores it and runs the test bodies, and JUnit 4 projects have no equivalent. This spec replaces that discovery with one that works for JUnit 4 and every JUnit 5 version without changing the project's dependencies. Execution, report parsing and test ids are unchanged. Per-case JDK and Python images (G4/G5) and effect-specific witnesses (G7) stay in the benchmark readiness inventory (IDEA-0005).

## Boundaries and design

Discovery is one fixed `/bin/sh` script with positional arguments. It runs the operator's Maven prefix with the reactor selection, `test-compile` and the pinned `maven-dependency-plugin:3.8.1:build-classpath` (`-Dmdep.includeScope=test`, output under the module's build directory), with Maven's console on stderr. It then runs the operator-pinned JUnit Platform console launcher (`junit-platform-console-standalone`, an absolute image path run by an absolute `java`) as `discover --details=flat` against `<module>/target/test-classes:<module>/target/classes:<test classpath>`, selecting exactly the two methods. The launcher brings its own Platform, Jupiter and Vintage engines, so the project's pinned JUnit 4.x or 5.x API on the classpath is discovered unchanged. `discover` runs no test body; class loading still runs static initialisers, as pytest collection imports modules.

`reports/junit_listing.py` reads the launcher's flat listing by unique id: a leaf must be a Jupiter method without parameters (`[engine:junit-jupiter]/[class:C]/[method:m()]`) or a Vintage test (`[engine:junit-vintage]/[runner:C]/[test:m(C)]`), any other leaf (parametrised, nested, dynamic or another engine's test) makes the listing inexact, and the count must equal the launcher's `tests found` summary. The runner then requires exactly the two ids, as for pytest; a missing method, a compile or classpath failure, or an inexact listing is a `collection_error` and nothing executes. Operator configuration adds `java`, `console_jar`, the pinned dependency plugin and the build directory. The operator's Maven prefix (`MavenRunnerConfig.command`) must be goal-free: every token after the binary is an option (`-B`, `-o`, `--file=<root>/pom.xml`, `-D…`), so no goal or phase can run a test before the listing; the runner appends `test-compile` for discovery and `test` for execution. The environment agent (SPEC-0029) admits a command that prints discovered ids; the runner accepts it and never executes or reinterprets it as a prefix, so its listing is always this prefix plus `test-compile` (an earlier rule refused any discovery command other than the prefix, which stopped every admitted case at its first run).

Native capabilities only: Maven, the dependency plugin and JUnit's own console launcher. The listing parser is the only new code and is bounded to that output format.

## Acceptance and validation

Offline: listings captured from real launcher runs against JSPWiki (JUnit 5.4.0) and a JUnit 4.12 project, refusals for inexact listings, the runner's discovery argv and its refusals over fake ports, and a real JUnit 4 Surefire 2.22 report. Host-only (not sandbox, not qualification): the Maven runner through real Maven and the launcher on unchanged POMs for JUnit 4.12/Surefire 2.22, JUnit 5.14.4/Surefire 3.6.0 (single and two-module) and JSPWiki at both commits with JUnit 5.4.0/Surefire 2.22.0.

Live: the launcher jar and the dependency plugin must be added to the Java toolchain image, hash-pinned, and the image re-qualified; then the runner runs in the SPEC-0032 workspace.

## Decisions and open questions

The dry-run path is removed rather than kept as an alternative, because the launcher covers every version it covered. Launcher 1.14.4 matches the qualified image's JUnit 5.14.4; it needs Java 8 or later at runtime, and its JUnit 4 support is through Vintage (JUnit 4.12 or later); JUnit 3 and TestNG are not covered. The plan is [PLAN-0045](../plans/PLAN-0045-version-independent-junit-discovery.md).
