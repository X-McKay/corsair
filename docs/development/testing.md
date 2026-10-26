# Development testing

This guide maps the current Just recipes to the boundary they exercise. It is not a replacement for the [CLI reference](../reference/cli.md), agent-evaluation guidance, or the current qualification record in [plans](../plans/README.md). Run commands from the repository root after [setup](setup.md).

## Fast local gates

```bash
just sync
just check
just -- test -q -W error
just build
```

`just sync` installs the locked development dependencies. `just check` runs the toolchain report (see [prerequisites and failure messages](setup.md#prerequisites-and-failure-messages)), Ruff lint, Ruff format check, Just formatting, `ty check --error-on-warning` across maintained source, tests, evaluators and developer scripts, and local Markdown link/anchor checks. `just test` (also `test-offline`) selects `not docker and not temporal and not live`; it includes the built-wheel resource test, which creates a fresh environment and loads the actual wheel outside the checkout. `just build` creates the source distribution and wheel.

Recipe arguments after `just -- RECIPE` go directly to pytest or the CLI. Use `-W error` for a strict qualification run; the recipes forward it rather than silently changing warning policy. Report test counts, deselections, skips, and warnings with the command result. A skip is an unexecuted boundary, not a pass.

`just docs-check` runs the maintained developer checker without services or network access. Offline tests also enforce forbidden package dependencies; they do not freeze every directory name for cosmetic reasons. See [local files](local-files.md) for temporary staging and retention.

## Test matrix

| Boundary | Command | Prerequisites and meaning |
| --- | --- | --- |
| Offline code, contracts, fixtures, package resources | `just -- test -q -W error` | No Docker, Temporal, or provider request. Validates the selected offline boundary only. |
| Native Docker observer | `just images` then `CORSAIR_TEST_TEMPORAL=1 just -- test-docker -q -W error` | A reachable reviewed daemon, `corsair-python:0.1`, and the local Temporal test server. `test-docker` sets `CORSAIR_TEST_DOCKER=1`, so a missing daemon/image fails rather than silently skips. |
| Long Docker probe deadline | `CORSAIR_TEST_LONG_PROBE=1 just -- test-docker -q -W error tests/integration/test_docker.py::test_real_docker_probe_deadline_can_exceed_120_seconds` | Explicit real-Docker opt-in only. The one-role regression sleeps 121 seconds, then must complete and clean up before its 180-second `probe_timeout_seconds` budget. Without this environment variable it skips and is not a passing native gate. Rebuild the trusted image with `just images` after changing the driver. |
| Durable workflows and replay | `just -- test-temporal -q -W error` | `test-temporal` sets `CORSAIR_TEST_TEMPORAL=1`; the fixture starts a real local Temporal test environment and runs ordinary typed activities. It does not run Docker target execution or a live model. |
| All native gates | `CORSAIR_LIVE_CONFIG=/operator/settings.json just -- test-all -q -W error` | `test-all` enables Docker and Temporal and installs the optional provider dependency. A real-provider smoke still requires the explicit operator settings path; without it, that test skips. |
| Isolated producer/auditor diagnostic | `just -- eval-agent AGENT DATASET --settings /operator/settings.json --repeats N` | Requires an operator-configured provider. Runs the production role factory against frozen inputs without target execution; it is not a whole-system result. |

`test-docker` also selects tests marked `temporal`; set `CORSAIR_TEST_TEMPORAL=1` as shown so those fixture-backed durable tests execute instead of skip.

### Concurrent suites on one daemon

Several worktrees may run `test-docker` against one Docker daemon at the same time. An operation id becomes the `corsair.operation` container label, and the operation-reconciliation gate refuses any operation whose label already exists on the daemon (`an uncommitted labeled sandbox exists; operation will not be replayed`, with `cleanup_confirmed` false). That gate is the behaviour under test, so the tests keep identities apart instead of relaxing it:

- Every operation id in [test_docker.py](../../tests/integration/test_docker.py) comes from the session-scoped `session_operation` fixture as `pytest-<12 hex>.<label>`, one random prefix per pytest session. Tests assert that format, not a literal id.
- Temporal workflow ids, run ids and task queues come from `temporal_id` in [workflow/temporal.py](../../tests/workflow/temporal.py), which is unique per call; each session also starts its own Temporal test server. Operation ids in the chain and CLI tests derive from those run ids.
- At session teardown the fixture lists labelled sandboxes whose operation id carries its own prefix, removes them by immutable id, and fails with their names, so a leak is never silent. It never touches another prefix, because another suite may still hold that identity. A start-of-session sweep would be a no-op for a fresh prefix. Containers left by older fixed-id runs are not removed and no longer collide. `test-live` selects only the live marker and installs the provider extra, but it neither creates credentials nor sets `CORSAIR_LIVE_CONFIG`.

The CI workflow uses the locked Nix shell. Linux amd64 covers offline/package, Docker/Temporal native conformance, and durable workflow jobs; macOS arm64 covers offline/package and Temporal. Hosted macOS does not stand in for physical Docker Desktop/Colima nested virtualization. See [platforms](../reference/platforms.md) for the support and host-qualification boundary.

## Frozen inputs and evaluation discipline

Treat `evals/fixtures` and dataset declarations as test inputs, not formatting targets or convenient examples. Fixture source hashes and line numbers bind a result to the observed target. Ruff excludes that directory so automatic formatting cannot rewrite it; `ty` and conformance tests still apply. Change a fixture, oracle, budget, prompt, source digest, or dataset only as a deliberate evaluated change, not to turn a failed run green.

The isolated evaluator reads each declared input and oracle once, verifies the exact bytes against its dataset digest, and keeps the oracle outside the agent packet. Preserve that separation in new evaluators. Test doubles may exercise a labelled unit/integration boundary, but they cannot create a Docker, Temporal, provider, or population-accuracy claim.

Use separate results for separate questions:

- Scripted ADK plus real Docker/Temporal tests validate composition, not live-model accuracy.
- Isolated live producer/auditor fixtures assess their stated frozen prompts and cases, not target execution or a population.
- A full live batch requires real worker, provider, Docker, Temporal, immutable evidence, and external scoring; retain operational errors and unavailable rows.

Docker, Temporal and live-provider gates run on a dedicated rig with a Docker daemon, a Temporal service and a configured model endpoint; the cloud development environment runs only the offline gates. A recorded count from one platform does not qualify another, and a figure from one revision is not a substitute for rerunning the affected gates on the current one. Current counts, unrun gates and open decisions are recorded in [current plans](../plans/README.md).

## Choosing and reporting checks

Start with the smallest meaningful test for the changed ownership boundary, then run affected consumers. Shared contracts, policy, source admission, evidence, runtime, workflow, package-resource, or configuration changes need broader checks. Docker/Temporal/live gates require the explicit host/service/provider prerequisites; do not replace a blocked gate with a mock and call it equivalent.

Record the exact command, environment gates (without secrets), result, elapsed time when material, skips/deselections, warnings, and unrun prerequisites in the active plan. Preserve failed attempts, immutable receipts, and unknown accounting. Never infer that zero reported tokens/cost means free execution when telemetry is missing.


## Directory ownership

`tests/` has only unit, integration, workflow, replay and security category directories. Root `conftest.py` and `__init__.py` are standard discovery/package files. Shared ADK test doubles live in [unit/adk.py](../../tests/unit/adk.py); real Temporal fixture registration and typed workflow doubles live in [workflow/temporal.py](../../tests/workflow/temporal.py). Integration/replay consumers import those single implementations; there is no separate tests/fixtures compatibility package.

`evals/` has datasets, evaluators, experiments, fixtures and baselines. The [evaluator guide](../../evals/evaluators/README.md) points to installed canonical evaluator/scorer code rather than duplicating it. Dataset/fixture/oracle/baseline bytes must survive organization-only changes unchanged. Ignored bytecode and obsolete cache-only folders are not components and are excluded from delivery.


A test belongs in the category of its primary behavior; markers declare dependencies. A sandbox security regression may therefore live in integration with the docker marker. Shared helpers stay in their owning category rather than being duplicated to make categories self-contained. Qualification receipts and candidate/promotion baselines are distinct under evals/baselines.
