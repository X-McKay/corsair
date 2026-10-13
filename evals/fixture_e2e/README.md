# Fixture end-to-end composition

E2E-0 from [SPEC-0031](../../docs/development/specs/SPEC-0031-fixture-direct-composition.md): issue identification, test planning, test authoring, frozen execution of the authored patch on the baseline and candidate revisions of the [SPEC-0018](../../docs/development/specs/SPEC-0018-native-two-test-fixture.md) pair, evidence assessment and the disposition gates, in direct mode.

`case.py` holds the hand-supplied environment evidence, the declared environment identity, the variant mapping and scripted plumbing models for each stage; none of it reaches a prompt except the issue, saved source and environment evidence. `reviewed.py` is the only host workspace and refuses every patch except the reviewed SPEC-0018 test bytes before execution.

```sh
PYTHONPATH=src:. .venv/bin/python -m evals.fixture_e2e.run --evidence .runs/fixture-e2e-<date>/scripted-001
PYTHONPATH=src:. .venv/bin/python -m evals.fixture_e2e.run --evidence .runs/fixture-e2e-<date>/live-001 \
  --provider-config <LocalModelConfig.json> --live identification,planning,authoring,assessment
```

Stages not named in `--live` are scripted. No component captures the planned witness outside the test process, so the gate verdict is at most `completed`/`inconclusive`/`not_verified`. A live author's own tests are refused by the reviewed workspace, so a fully live run stops at authoring until the sandbox test workspace exists. Each run writes `configuration.json`, one receipt per stage attempt (usage, messages, elapsed time, failure), `native-runs.json` (every native runner observation by purpose and operation, development and failed runs included: workspace source and test artifact references, discovery and execution commands, complete receipts with stdout/stderr bytes as digest plus base64, JUnit artifact reference and parsed cases, independent of what the assessment agent reads) and `result.json`; existing evidence directories are refused.
