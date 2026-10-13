# Fixture chain evaluation

Native Pydantic Evals over the whole E2E-0 composition ([SPEC-0031](../../docs/development/specs/SPEC-0031-fixture-direct-composition.md)) on variants of the reviewed [SPEC-0018](../../docs/development/specs/SPEC-0018-native-two-test-fixture.md) pair, as designed in [SPEC-0035](../../docs/development/specs/SPEC-0035-assessment-evals-and-durable-chain.md).

`Case.inputs` (`ChainInput`) is evaluator-owned: which reviewed variant (`vulnerable`/`fixed`) each purpose's fresh workspace holds (`development`, `baseline`, `candidate`), or an issue whose source is absent. Agents never see it; the issue carries only the baseline variant's saved source and the fixture_e2e environment evidence. `ChainOracle` holds the expected stop stage, gate triple and whether the assessment is admitted.

| Case | Mapping | Expected now | Once SPEC-0033 witness capture lands |
| --- | --- | --- | --- |
| `vulnerable_to_fixed` | vulnerable → fixed | completed / inconclusive / not_verified | completed / reproduced / verified |
| `fixed_to_vulnerable` | fixed → vulnerable | completed / inconclusive / not_verified | completed / not_reproduced / not_verified |
| `both_vulnerable` | vulnerable → vulnerable | completed / inconclusive / not_verified | completed / reproduced / not_verified |
| `both_fixed` | fixed → fixed | completed / inconclusive / not_verified | completed / not_reproduced / not_verified |
| `source_absent` | issue without `documents.py` | stops at identification | unchanged |

Every revision run carries the SPEC-0033 operator probe, so the gate admits a reproduced finding or verified fix only from an admitted witness, and the variants are discriminated by it.

The task builds a `FixtureCase` like `evals/fixture_e2e/case.py` with the case's mapping and its own runner factory over `ReviewedWorkspace`/`ReviewedLocalExecution`, then awaits the injected composition `run(case, models, runners, budget)`, `run_direct` by default; durable mode passes another coroutine with the same signature. Assertions: `stopped_as_expected`, `gate_matches`, `assessment_admitted`, `proposal_matches_gate`; per-stage requests, tool calls, tokens, output corrections and elapsed seconds are recorded as attributes.

```sh
PYTHONPATH=src:. .venv/bin/python -m evals.fixture_chain.evaluate --evidence .runs/fixture-chain-<date>/scripted-001
PYTHONPATH=src:. .venv/bin/python -m evals.fixture_chain.evaluate --evidence .runs/fixture-chain-<date>/live-001 \
  --provider-config <LocalModelConfig.json> --live identification,planning,assessment
```

Stages not named in `--live` reuse the fixture_e2e scripted plumbing (an abstaining scripted identification for the absent-source case; the scripted assessment proposes the oracle gate triple). A live author's own tests are refused by the reviewed host workspace, so live authoring stops the chain there. Each attempt keeps `run-<uuid>/` with `inputs.json`, one receipt per stage attempt, `native-runs.json` (every runner observation by purpose) and `result.json`, beside `configuration.json` and the native `report.json`; existing evidence directories are refused. Defaults: one repeat, concurrency one, `CompositionBudget()`, no task retry.
