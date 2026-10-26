# Evaluators

Corsair's executable evaluators are installed package code, shared with the CLI and native result rescoring. This directory describes their ownership and criteria; it does not contain a second copy, compatibility launcher, generated oracle or placeholder implementation.

- [Isolated agent evaluator](../../src/corsair/evaluation/agents.py) invokes the actual producer/auditor factory against digest-verified frozen inputs. The producer diagnostic uses exact canonical payload matching; the auditor diagnostic compares its typed review decision. Oracles stay local to the evaluator, outside agent inputs.
- [Dataset loaders](../../src/corsair/evaluation/datasets.py) read each manifest's request, input and oracle bytes once and verify their declared digests before any evaluator parses them, returning oracle data only to the evaluator caller; `corsair dataset validate` runs the same loaders offline.
- [Domain scorer](../../src/corsair/evaluation/scoring.py) validates persisted native evidence, binds case/configuration/scope, checks oracle dispositions and fixed-result evidence, and retains invalid positives, operational errors and unavailable results in the report denominator. It is the same scorer used by eval/rescore, not another grading engine.
- [Candidate replay](../../src/corsair/evaluation/replay.py) runs an isolated producer report's mismatching proposals through the trusted native verification path in Docker and records whether each pair demonstrates. It never reads or writes an oracle and never changes a row's pass/fail; a human decides whether to admit a demonstrating payload.
- [Intake evaluator](../../src/corsair/evaluation/intake.py) scores the frozen scanner-intake dataset (`intake.json`): it admits each digest-pinned source tree, converts every scan-report finding to a candidate request and compares its admissibility outcome (`admissible`, `admissible:recipe_function` or `blocked:REASON`) with an external per-finding oracle. It runs no model, container or service; `corsair intake` is the same assessment on one report without an oracle.

## Candidate expanded diagnostics

`producer-expanded.json` retains `case01` with its original byte identities and adds `producer02` (`pathlib.Path` / `read_document`) and `producer03` (`os.path.join` / `fetch_record`). The new recipes have distinct functions and fixed keyword arguments. Both probe exact scalar path values; neither permits a keyword-argument mapping as a payload.

`auditor-expanded.json` retains `audit01` and `audit02` with their original byte identities and adds `audit03`, a coherent source-grounded parent-traversal claim expected to be accepted, and `audit04`, a semantically fabricated SQL claim expected to be rejected. Decision labels remain in external oracle files. These four AI-authored cases are candidate diagnostics pending human review, not human-labelled, held-out, promoted, or population baselines.

`auditor-rubric.json` adds `audit05` to `audit11`: one packet for each of `R1` to `R4` failing on its own, one `INSUFFICIENT_CONTEXT` packet and two acceptances of different path-handling flaws. Each oracle names a `decision` and the decisive `rule`, and the evaluator scores both only when the oracle has a `rule` (otherwise the decision alone decides, so `auditor-dev.json` and `auditor-expanded.json` score as before). These seven are also AI-authored candidate diagnostics pending human review.

The accompanying frozen consistency test parses packets with canonical Pydantic contracts, validates raw packet digests through the actual isolated evaluator loader, and admits producer source bytes through the canonical snapshot loader. It does not import or execute any fixture target, invoke a model, or claim native evidence.

From the repository root, run an isolated diagnostic only with explicitly configured provider access:

```bash
just -- eval-agent producer evals/datasets/producer-dev.json \
  --settings /operator/settings.json --repeats 3
just -- eval-agent auditor evals/datasets/auditor-dev.json \
  --settings /operator/settings.json --repeats 3
```

A composed dataset requires real Temporal, a worker, Docker and the selected provider:

```bash
just -- eval evals/datasets/dev.json --settings /operator/settings.json \
  --output .runs/evaluations/dev.json
```

[Datasets](../datasets/) declare frozen identities; [fixtures](../fixtures/) hold inputs, targets and oracles; [baselines](../baselines/README.md) hold sanitized comparisons and promotion decisions; [experiments](../experiments/README.md) record intentional prompt/configuration changes. No policy denial, malformed output, failed control or unknown execution is a successful security result. Do not silently edit labels or promote small diagnostic scores into population accuracy.

See the [agent evaluation guide](../../docs/agents/evaluations.md), [testing guide](../../docs/development/testing.md) and [current work](../../docs/plans/README.md) for the distinctions between deterministic fixture tests, isolated live agents, native conformance and composed evaluation.
