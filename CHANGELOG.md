# Changelog

This file records released changes. It is not a declaration that the working tree has been committed, published or released. Implementation and qualification records live in [plans and archives](docs/plans/README.md).

## Unreleased

Improvement loop, rounds 1 and 2 ([PLAN-0002](docs/plans/active/PLAN-0002-improvement-loop-rounds-1-2.md)):

- Accuracy: a flat `ProducerDecision` output object (the `RootModel` declaration could never be satisfied through ADK's `set_model_response` on the LiteLLM route; live producer-dev went from 0/3 to 3/3); loader-free agents (the auditor is tool-less, the producer has only `read_file` and `list_files`, the procedure is preloaded, per-class references are selected by trusted code into the packet); the auditor rubric with rule ids `R1` to `R4`; a `provider_max_tokens` gate; a pre-model `target_binding` gate, derivation of a missing finding line from the recipe function, and binding of declared lines to the statement coverage reports; one time-bound policy (`request <= episode < activity`).
- Runtimes: a second Python recipe (`python.command_sentinel/1`) and one qualified corpus row each for JavaScript, Ruby, Java, Perl and C, each as a `Case.recipe` union member with its own trusted driver and image (`Settings.images`, `just images`).
- Evaluation and iteration: `corsair compare`, per-case and Markdown reports, the gate ledger (composed and isolated rows), `corsair runs`, `inspect --evidence`/`--explain`, `corsair explain`, `corsair dataset validate` / `replay-candidates`, `corsair intake`, `corsair agent preview`, `corsair doctor --model`, family/split checks, the `auditor-rubric` and `intake` datasets, `just live-agent` / `live-chain` records, `just settings-init` / `temporal-up` / `worker-up` / `demo`, `just toolchain`, and session-scoped Docker test ids.
- Latency and size: lazy CLI imports (`--version` 629 ms to 39 ms), snapshot reads once per listing (`list_files` 3.5 s to 28 ms on 991 files), the driver's in-process coverage report with `sys.monitoring` (per-role container 418 ms to 284 ms), worker slot settings; the dead DuckDB scorecard module and its dependency removed.

Initial pilot: two Google ADK agents (payload-pair producer, tool-less reject-only auditor) over a deterministic coverage-gated kernel that decides one of six labels in code, with each agent episode run as one Temporal activity. See the [architecture overview](docs/architecture/overview.md) and [current work](docs/plans/README.md).
