# Benchmark cases and denominator report

Offline step 1 of [IDEA-0005](../../docs/development/ideas/IDEA-0005-benchmark-readiness-gaps.md): it joins every row of [`benchmarks/candidate-cases.json`](../../benchmarks/candidate-cases.json) with any manifest under `benchmarks/cases/<dir>/case.yaml` and counts the whole denominator. It runs no case and is not connected to the chain.

A manifest has two parts. `agent` is the only part an agent may see: neutral issue text, scope, repository, baseline and candidate commits, language and build system. `evaluator` holds the dataset case id, CWE, fix reference, frozen reference test digest, expected per-revision outcomes (`basis: hypothesis` until executed, with a `ChainOracle` once the gate is known), split, admission status and the blocking IDEA-0005 gaps. Unknown facts are `null`.

`load()` refuses a manifest whose case id is not in the inventory or already has a manifest, that disagrees with the inventory's repository, fix commit, language, build system or CWE, whose reference test bytes differ from the frozen digest, or whose agent issue text names the case id, the advisory id (any CVE or GHSA id) or a dataset. Rows without a manifest take the operator-owned `DEFAULT_BLOCKING` gaps for their language. `agent_input()` builds an `IssueAnalysisInput` from the agent part alone; repository source is not mapped yet (G2b).

```sh
PYTHONPATH=src:. .venv/bin/python -m evals.benchmark.report               # markdown table
PYTHONPATH=src:. .venv/bin/python -m evals.benchmark.report --format json
```

Counts are inventory metadata, not executions: zero of the 50 cases are admitted or have run.
