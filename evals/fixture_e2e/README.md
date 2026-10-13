# Fixture end-to-end composition

E2E-0 from [SPEC-0031](../../docs/development/specs/SPEC-0031-fixture-direct-composition.md): issue identification, test planning, test authoring, frozen execution of the authored patch on the baseline and candidate revisions of the [SPEC-0018](../../docs/development/specs/SPEC-0018-native-two-test-fixture.md) pair, evidence assessment and the disposition gates, in direct mode.

`case.py` holds the hand-supplied environment evidence, the declared environment identity, the variant mapping and scripted plumbing models for each stage; none of it reaches a prompt except the issue, saved source and environment evidence. `reviewed.py` is the only host workspace and refuses every patch except the reviewed SPEC-0018 test bytes before execution.

```sh
PYTHONPATH=src:. .venv/bin/python -m evals.fixture_e2e.run --evidence .runs/fixture-e2e-<date>/scripted-001
PYTHONPATH=src:. .venv/bin/python -m evals.fixture_e2e.run --evidence .runs/fixture-e2e-<date>/live-001 \
  --provider-config <LocalModelConfig.json> --live identification,planning,authoring,assessment
```

Stages not named in `--live` are scripted. Every run requests the [SPEC-0033](../../docs/development/specs/SPEC-0033-witness-capture.md) operator probe witness for the approved envelope, so the gate can permit `reproduced`/`verified`; the probe is tamper-evident, not tamper-proof. The CLI uses the reviewed host workspace, which refuses a live author's own tests.

`docker.py` runs every purpose in a fresh offline container of the local CPython 3.12 toolchain image under plain Docker ([PLAN-0081](../../docs/development/plans/PLAN-0081-docker-e2e-route.md)), so a live author's tests execute without a kind/OpenShell cluster. It is unqualified, risk accepted: no OpenShell policy, gateway or admission stands behind it, and its `configuration.json` and `result.json` say so (`runner.route = docker`, `runner.qualification = unqualified`).

```sh
make toolchain-images TOOLCHAINS=python   # then {"cpython-3.12-pytest": "<config_id from .cache/toolchains/python/build.json>"}
PYTHONPATH=src:. .venv/bin/python -m evals.fixture_e2e.run --sandbox docker --images <images.json> \
  --evidence .runs/fixture-e2e-<date>/docker-001 [--provider-config <config.json> --live identification,planning,authoring,assessment]
```

`sandbox.py` runs every purpose in a fresh OpenShell sandbox through the [SPEC-0032](../../docs/development/specs/SPEC-0032-openshell-test-workspace.md) test workspace, so a live author's tests execute there and never on the host ([PLAN-0034](../../docs/development/plans/PLAN-0034-fixture-e2e-sandbox-runner.md)). It needs a qualified kind/OpenShell runtime, set up as in the [toolchain runbook](../../docs/runbooks/openshell-toolchains.md) (`make toolchain-images` builds the images that `make toolchain-images-load` puts on the node, so it comes first on a fresh worktree); the live gate runs an all-scripted control first, then the live runs:

```sh
make qualify-fixture-e2e CORSAIR_NETWORK_RUN=<network evidence> CORSAIR_PROVIDER_CONFIG=<LocalModelConfig.json> \
  CORSAIR_E2E_RUNS=2 CORSAIR_E2E_LIVE=identification,planning,authoring,assessment
``` Each run writes `configuration.json`, one receipt per stage attempt (usage, messages, elapsed time, failure), `native-runs.json` (every native runner observation by purpose and operation, development and failed runs included: workspace source and test artifact references, discovery and execution commands, complete receipts with stdout/stderr bytes as digest plus base64, JUnit artifact reference and parsed cases, independent of what the assessment agent reads) and `result.json`; existing evidence directories are refused.
