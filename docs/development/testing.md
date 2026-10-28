# Development testing

This guide maps current Just recipes to the boundary they exercise. It does not replace the [CLI reference](../reference/cli.md), [evaluation guidance](../agents/evaluations.md), [language guide](../guides/languages.md), or the [PLAN-0127 record](../plans/archive/plans/PLAN-0127-outcomes-node-java.md), which records actual results and pending gates. Run commands from the repository root after [setup](setup.md).

## Fast local gates

```bash
just sync
just check
just -- test -q -W error
just build
```

`just check` runs Ruff lint/format checks, Just formatting, `ty check --error-on-warning`, and local Markdown link/anchor checks. `just test` (also `test-offline`) selects `not docker and not temporal and not live`; it includes the built-wheel resource test. Report counts, deselections, skips, warnings, and unrun prerequisites. A skip is not a completed boundary.

`just docs-check` runs the maintained local documentation checker. It does not start a service, build an image, or execute target source.

## Current matrix

| Boundary | Command | Prerequisites and meaning |
| --- | --- | --- |
| Offline code, contracts, fixtures, and package resources | `just -- test -q -W error` | No Docker, Temporal, or provider request. |
| Reviewed observer images | `just images` | Aggregates `images-python`, `images-node`, and `images-java`; target source is not part of these builds. |
| One image with a literal tag | `just images-python TAG`, `just images-node TAG`, or `just images-java TAG` | Optional literal tag is forwarded to that observer image task. |
| Node native observer | `CORSAIR_TEST_NODE=1 just -- test-docker -q -W error tests/integration/test_node.py` | Reviewed Docker daemon and selected Node image; exercises the fixed `.mjs` ESM/JSON observer and its native JUnit/LCOV receipt projection. |
| Java native observer | `CORSAIR_TEST_JAVA=1 just -- test-docker -q -W error tests/integration/test_java.py` | Reviewed Docker daemon and selected Java image; exercises the fixed static `String`/`String` observer, JUnit Platform, and JaCoCo receipt projection. |
| Shared language consumers | `CORSAIR_TEST_NODE=1 CORSAIR_TEST_JAVA=1 just -- test-docker -q -W error tests/integration/test_language_chain.py` | Reviewed Docker daemon, both selected images, and local Temporal test support where selected. |
| Durable workflows and replay | `just -- test-temporal -q -W error` | Real local Temporal activities and replay; it does not execute a target or call a provider. |
| All local native selections | `CORSAIR_LIVE_CONFIG=/operator/settings.json just -- test-all -q -W error` | Enables Docker/Temporal and provider extras. Node/Java selection still requires their explicit environment gates. |
| Isolated producer/auditor diagnostic | `just -- eval-agent AGENT DATASET --settings /operator/settings.json --repeats N` | Explicit provider configuration; no target execution. |

`test-docker` sets `CORSAIR_TEST_DOCKER=1`. CI's native-conformance job builds the default three observer images and sets `CORSAIR_TEST_TEMPORAL=1`, `CORSAIR_TEST_LONG_PROBE=1`, `CORSAIR_TEST_NODE=1`, and `CORSAIR_TEST_JAVA=1` before `just test-docker`. This is a selected CI boundary, not a substitute for the result record or final qualification.

`corsair doctor --settings PATH` is a baseline Python infrastructure check. It does not select a recipe image, test a provider, execute a target, validate receipts/coverage/cleanup, or qualify a selected recipe.

## Frozen inputs, outcomes, and replay

Treat `evals/fixtures` and dataset declarations as frozen test inputs, not formatting targets. Their declared source/oracle hashes and line numbers bind a result to the observed target. The formal pre-outcome fixture files and their hashes remain unchanged; legacy result/1 inputs and oracles remain separate from version-2 assessment cohorts.

The two genuine marker-absent histories in `tests/replay/histories/` cover preserved pre-assessment completion forms. Their earlier replay result does not stand in for the current full requalification; retain that status in [PLAN-0127](../plans/archive/plans/PLAN-0127-outcomes-node-java.md).

`corsair.result/2` outcome completion requires `COMPLETED` execution, a healthy control, a valid actually executed adversarial held/disclosure result as applicable, accepted audit, validated native receipt/coverage, and confirmed cleanup. `NOT_DEMONSTRATED` additionally requires the full diverse finite protocol to complete. Errors, audit rejection, repeated candidates, unavailable services, missing evidence, and uncertain cleanup remain unresolved.

## Reporting

Start with the smallest meaningful test and affected consumers. Docker, Temporal, and provider checks require explicit prerequisites; do not replace an unavailable boundary with a mock and call it equivalent. Record exact command, environment gates without secrets, image/configuration identity, outcome, skips/deselections, warnings, and unrun prerequisites in [PLAN-0127](../plans/archive/plans/PLAN-0127-outcomes-node-java.md). Preserve failures and historical records exactly.
