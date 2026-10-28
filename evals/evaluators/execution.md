# Recipe-free role evaluator

Executable scoring lives in [`corsair.evaluation.execution`](../../src/corsair/evaluation/execution.py). The [four-case candidate cohort](../datasets/execution-roles.json) freezes separate producer/auditor inputs and evaluator-only labels with hashes. These authored cases are pending human review, not held-out baselines.

The producer score checks canonical completion, revision, source-location association and source/target references in proposed material. It does not prove that generated tests exercise the claimed behavior. Auditor scores compare exact categorical decisions and reasons; a correct rejection with different reasons remains an exact mismatch. Neither score is vulnerability accuracy.

```bash
uv run --locked python -m corsair.evaluation.execution \
  evals/datasets/execution-roles.json --settings /operator/settings.json \
  --repeats 1 --seconds 60 --output .runs/execution-evaluation/report.json
```

This invokes genuine ADK role factories independently with frozen source readers, without target execution or Temporal. It uses explicitly configured producer/auditor models. Oracles never enter role packets. Provider failures, malformed output and unrun attempts remain explicit; progress is initialized before the first episode. Usage is retained in private episode artifacts; cost remains unknown.

Actual Docker conformance, Temporal/replay, installed resources and full live-chain quality have separate gates. See [the current implementation record](../../docs/plans/active/PLAN-0133-recipe-free-implementation.md). No baseline promotion is implied by a report's filename or passing schema/scorer tests.
