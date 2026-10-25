# Code quality and review

The 2026-10-25 review found and removed the unused `list_snapshot_paths` export, its redundant preparation binding, an immediately discarded Docker image-error field, duplicate CLI request-loading code and repeated token-total calculations. The stale `test-config` Makefile alias was removed. GitHub CI action references were refreshed to exact releases using Node 24. Historical dated plans and qualification records are retained as history, not executable compatibility paths.

The CLI dispatcher went from 221 lines to 8. Its named handlers each own one operator command; `_result_from_store` owns receipt retrieval, `validate_run_id` owns ID validation, and the shared request loader owns client-edge lexical path resolution. The isolated evaluator has separate frozen-file loading, model invocation, oracle comparison, row recording and batch coordination functions. Temporal activity admission and final recording are separate methods. The workflow's round coordinator and Docker container lifecycle remain cohesive ownership boundaries rather than being split into a generic engine or many one-line wrappers.

Small explicit composition was the simpler pattern here. No mixin, speculative backend, second agent loop or custom parser framework was introduced. The ADK factories still use native model/event types; Docker uses the native client and explicit SDK exceptions; Temporal still owns durable scheduling, retries and cancellation. The necessary pinned ADK invocation-stop bridge remains explicitly isolated.

## Required local and CI checks

```bash
just sync
just check        # Ruff lint + formatting + ty
just test         # offline tests, including fresh installed-wheel resources
just images
CORSAIR_TEST_TEMPORAL=1 just test-docker
just test-temporal
```

Ruff 0.17.2 and ty 0.0.91 are pinned in the uv lock. `just check` runs `ruff check src tests evals`, `ruff format --check src tests evals`, and `ty check --error-on-warning`. Ruff includes unused-argument checks. ty includes runtime source, all tests and all evaluation Python and targets Python 3.12. All 33 initial ty diagnostics were resolved by real annotations, imports and runtime narrowing; there are no broad type ignores or runtime/test typing exclusions.

The only Ruff exclusion is immutable `evals/fixtures`, because formatting target code would change declared target line numbers and canonical source hashes. These fixtures remain checked by ty and frozen-hash/native conformance. Never change a frozen input merely to make an experiment pass.

A dead-code scan is a candidate list, not deletion authority. Pydantic validators, schema/enum members, Temporal registrations, native logging attributes and ADK callbacks are consumed dynamically or preserve wire contracts. The reviewed 100%-confidence scan is clean; lower-confidence candidates were checked against callers and SDK/schema usage. Required SDK method parameters in labelled test doubles remain explicit, rather than altering the production interface to silence a scan.

## Logging and errors

The CLI and evaluator share `safe_error_detail`: Pydantic failures identify the failed fields without rejected input values. JSON stdout contains command results only; safe JSONL stderr events contain operational identity, phase, attempts, time and usage. External SDK diagnostics retain their logger/severity and exception classification, but never forward request bodies or exception locals.

Console logging is installed before optional mirror-file I/O. A bad `--log-file` path therefore still produces a safe JSONL `cli.failed` event and exit 2. New mirror files are created with mode 0600; existing file permissions remain the operator's responsibility. Unknown accounting remains null. Completed failures, cancelled waits, unavailable progress and provider-policy blocks remain distinct from success. Ctrl+C still detaches a client without silently cancelling its remote workflow.

## Final qualification

The strict full run passed **105 tests in 110.07 seconds**, with Docker, Temporal and a genuine live-auditor gate enabled, no skipped tests, and warnings treated as errors. Ruff lint/format and warning-failing ty passed. The full suite exercises the actual built wheel installed into a fresh environment outside the source checkout. Real Docker evidence, workflow history replay, cancellation/restart, CLI process/animation/JSON checks and saved-evidence scoring remained in that run.

The additional frozen auditor evaluation passed **6/6 attempts**: two labelled cases repeated three times, six real model calls, no operational failures, and 12 parseable JSONL lifecycle events. Its dataset and prompts were not changed by the refactor. This small fixture result does not establish population accuracy or full live-producer qualification.

Frozen request/oracle loading now reads each file once and parses those exact verified bytes. This reduces file reads per case from four to two and closes the prior hash/parse reread gap. A same-host, five-repeat deterministic microbenchmark measured roughly **5.6% lower dataset-loading time** and **8.5% lower count-aggregation time**. These are small local-path measurements, not a claim about model, Docker or Temporal latency. Complete agent runtime remains dominated by those external operations.

The live security producer is still provider-policy blocked and was not retried or replaced. General hostile-interpreter attestation and host-loss recovery of a separate local artifact filesystem remain outside the pilot qualification. See [the risk assessment](../src/corsair/runtime/risk.md), [CLI reference](cli.md), and [latest handoff](development/handoffs/HANDOFF-0140-code-quality.md) before expanding scope.
