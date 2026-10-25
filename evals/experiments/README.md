# Evaluation loops

Use the same production factories and authoritative scorer. A new prompt/model/tool change requires fresh agent invocations; changing an image/driver requires native replay of frozen submissions; a policy-only change may rescore saved observations; workflow changes require native Temporal history replay.

## Isolated agents

```bash
uv run --locked --extra providers python evals/evaluators/agents.py producer \
  evals/datasets/producer-dev.json --settings settings.json --repeats 3
uv run --locked --extra providers python evals/evaluators/agents.py auditor \
  evals/datasets/auditor-dev.json --settings settings.json --repeats 3
```

These are live-model/fixture evaluations. Producer cases check the frozen intended benign/adversarial payload mechanism, not the target's vulnerability. Auditor cases check independent decisions on source and submitted payloads, with no observation or expected label in the model packet. They are diagnostic and are not native-workspace, host-loss or production accuracy evidence.

## Whole system

Run `corsair eval evals/datasets/dev.json --repeats 3 --settings settings.json` with an actual Temporal worker and Docker image. The scorer rejects positive results without admissible observation/audit evidence, records failures/unavailable results in the denominator, and distinguishes acceptable abstention from correctly resolved findings. Related source/fix variants stay within one family-grouped split.

Compare identical source, finding, recipe, dataset, schema, model configuration, instructions, tool and budget identities. Report repeat count and cohort. Native response usage is recorded when available; token/cost unknowns stay null. No automatically promoted baseline, LLM-written oracle, or policy/optimizer clearance is implemented.

If a runtime tampering test passes a deliberately forged report, do not treat that as a benchmark win: stop admission, inspect the trusted observation boundary, add a regression test, and qualify a stronger recipe.
