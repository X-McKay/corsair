# Benchmarks

One-off measurement harnesses kept so a recorded figure can be re-measured. They are not gates: no `just` recipe runs them, and their numbers describe the host they ran on. Run each from the repository root inside the Nix shell. Neither calls a model, runs target code or connects to a configured Temporal address.

| Script | Measures | Recorded results |
| --- | --- | --- |
| [`measure_eval_concurrency.py`](measure_eval_concurrency.py) | Evaluation-batch wall time against `--concurrency` and the worker's activity slots. It starts its own local Temporal test server and runs the production worker composition, real activities, source admission and evidence verifier; only the inference and sandbox ports are doubles that sleep a fixed time, so the figures measure coordination and slot limits, not model or container cost. [`tests/workflow/test_worker_concurrency.py`](../../tests/workflow/test_worker_concurrency.py) imports its doubles. | `eval-concurrency` row of [PLAN-0002](../../docs/plans/active/PLAN-0002-improvement-loop-rounds-1-2.md); sizing guidance in [deployment](../../docs/guides/deployment.md#size-worker-concurrency). |
| [`profile_source_snapshot.py`](profile_source_snapshot.py) | Local source admission and snapshot reads on a synthetic Python tree near the admission limits (default 990 files, about 7 MiB, under `.work/source-profile`): first and repeated admission, `prepare_case`, reader construction, `read_file` and `list_files` calls, and that a symbolic link, a FIFO and an oracle file each make admission refuse the tree. | `prepare-snapshot-profile` row of [PLAN-0002](../../docs/plans/active/PLAN-0002-improvement-loop-rounds-1-2.md). |

```bash
uv run --locked python scripts/benchmarks/measure_eval_concurrency.py --slots 4 16
uv run --locked python scripts/benchmarks/profile_source_snapshot.py --runs 3
```

`measure_eval_concurrency.py` takes `--cases`, `--concurrency`, `--slots`, `--episode-seconds` and `--role-seconds`; `profile_source_snapshot.py` takes `--root`, `--files`, `--bytes`, `--runs`, `--reads` and `--lists`. Each prints its own `--help`.

Request sizes are not measured here: `corsair agent preview ROLE REQUEST` renders what a role receives with byte and token counts ([CLI reference](../../docs/reference/cli.md#agent-preview-role-request)).
