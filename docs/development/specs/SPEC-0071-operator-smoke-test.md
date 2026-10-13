---
id: SPEC-0071
kind: spec
title: Operator smoke test as the environment baseline for projects with no tests
status: draft
updated: 2026-10-13
related: [SPEC-0029, SPEC-0068, SPEC-0069, SPEC-0067, PLAN-0078]
---

# Operator smoke test as the environment baseline for projects with no tests

## Goal and scope

The environment agent (SPEC-0029) returns ready only after one existing test is discovered and passes, and planning refuses an environment with no baseline. No SPEC-0067 corpus project ships a test, and many real repositories are the same, so every such case stops at the environment stage. Al chose to generalise Corsair (decision card, 2026-10-13 15:51Z) and kept the approach at 16:54Z. This spec adds an operator-owned smoke test per admitted framework that the agent may use as the baseline only when no project test runs.

Out of scope: a smoke test that imports the project's code (the environment stage runs before identification, so it has no target), frameworks the environment agent does not admit, and any change to the two native issue-validation tests.

## Boundaries and design

**Templates.** The smoke template is data on the framework row in `deploy/runtime-matrix.yaml` (`smoke`: path, test id, content), the one operator table that already names each framework's runner and images; rows with one name carry one template, and the loader refuses a mismatch. Conventional paths: `tests/test_corsair_smoke.py` (pytest), `src/test/java/CorsairSmokeTest.java` (JUnit 5 and JUnit 4), `t/corsair_smoke.t` (TAP), `__tests__/corsair_smoke.test.js` (Jest), `test/corsair_smoke_test.rb` (Minitest). Each is one trivially passing test that uses only the framework. Nothing is baked into an image: a new framework row adds its template as data, and no code is keyed on a language.

**Offer.** Runtime selection returns the template of each framework row it admitted on the selected image (`RuntimeOutcome.smoke_tests`, built by `nodes/runtime/environment.py` `smoke_tests`); two admitted frameworks sharing a path (JUnit 4 and 5) offer neither. `EnvironmentInput.smoke_tests` carries it to the agent, and the `Preparation` port writes it beside the captured commit (`prepare(..., overlay=)`, `PatchFile`s; the OpenShell adapter refuses an overlay path the capture already has before creating a sandbox). With nothing offered, behaviour is unchanged.

**Admission.** The skill tells the agent to prefer a project test and use the smoke test only when none is discovered and passes, with its id and path exactly. Trusted finalization refuses a baseline on a smoke path whose framework or id differs, a smoke baseline when the run's own discovery output names any other test (`frameworks.py` `project_tests`, using each framework's id grammar; Jest's absolute `--listTests` paths compared by their repository suffix), and approved test paths that name the smoke file. Every other ready rule (recipe, build, discovery listing the id, exactly one passed test) is unchanged. `ReadyEnvironment.baseline_basis` is set by trusted code: `project_test` or `operator_smoke`.

**Recording.** With `operator_smoke`, the smoke file joins the planning and authoring inventory through the same baseline-file path #106 added for a project baseline (its saved source is the operator template, since the capture does not hold it), never identification's, and adds the limitation that the baseline shows the runtime, framework and discovery work after setup, not that the project's code loads. The smoke file is never part of the frozen two-test patch.

## Acceptance and validation

- Every admitted framework has a template its own baseline rule accepts; the Python, Perl and Ruby templates pass under their native runners on the host.
- A chain run with no project test reaches the gates on the smoke baseline, records `operator_smoke` and the limitation, and shows the smoke file to planning only.
- A smoke baseline is refused when discovery lists a project test, and a baseline on the smoke path with another id is refused; a project baseline records `project_test`.
- `make eval AGENT=environment` scripted stays 16/16; the live environment eval reruns against its baseline when the model is free.

## Decisions and open questions

- The smoke file is written up front rather than after a discovery that lists nothing, since the sandbox is prepared once; the agent's choice is constrained by the skill and recorded in `baseline_basis`.
- Open: Jest and JUnit templates not yet run in their images (no Docker in this container); a project-import smoke variant once a target is known; whether the kick-off note's per-case result line takes `baseline_basis` as is.
