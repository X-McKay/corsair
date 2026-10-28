# Agent evaluations

Agent evaluation has distinct levels. Keep deterministic native-ADK tests, isolated live-model fixture diagnostics, and composed Docker/Temporal evaluations separate. The active [PLAN-0127 record](../plans/archive/plans/PLAN-0127-outcomes-node-java.md) contains actual results and current pending gates.

| Level | What runs | What it establishes |
| --- | --- | --- |
| Native test double | `ScriptedLlm` with real ADK runner/factories. | Factory, schema, tool, callback-budget, and consumer coverage. |
| Isolated agent evaluation | Installed production factory/native runner against frozen input and an explicit live model. | A role's bounded output against its frozen diagnostic oracle. |
| Composed evaluation | Worker, Temporal workflow, recipe-native Docker observer, immutable artifacts, policy, and external scorer. | The stated end-to-end cohort and its evidence/operational rows. |

None of these levels silently establishes another one.

## Frozen inputs and historical records

The evaluator reads each declared request and oracle once and verifies its digest before parsing. Oracles remain evaluator-owned; they are not agent, tool, or workflow input. Provider blocks, malformed output, unavailable rows, unexpected exceptions, and unknown usage/cost remain explicit.

Existing `corsair.result/1` records, legacy oracles, and frozen input bytes retain their original wire shape and interpretation. Formal pre-outcome fixture hashes remain frozen. The two genuine marker-absent pre-outcome histories under `tests/replay/histories/` exercise both preserved v1 completion forms; their earlier recording stage is separate evidence; the final physical-Mac suite also replayed them, as recorded in [PLAN-0127](../plans/archive/plans/PLAN-0127-outcomes-node-java.md).

New assessment datasets use `corsair.result/2` with separate `corsair.assessment-oracle/1` files. A dataset cannot mix legacy and assessment oracle kinds.

## Paired assessment evaluation

A completed assessment requires `execution_status: COMPLETED`, validated immutable receipt/coverage, confirmed cleanup, and an accepted independent audit.

- `DEMONSTRATED` requires a healthy control plus a valid, actually executed adversarial disclosure.
- `NOT_DEMONSTRATED` requires a healthy control plus valid, actually executed held adversarial attempts through the entire diverse finite protocol.

For the negative outcome, the workflow continues after a held pair. A producer abstention, repeated adversarial candidate, evidence/provider/execution error, rejected or missing audit, timeout, unavailable service, or uncertain cleanup makes the protocol unresolved; it does not become `NOT_DEMONSTRATED`. Follow-up feedback to the producer is mechanical and outcome-blind, never an evidence label.

`NOT_DEMONSTRATED` is limited to the submitted protocol. It is not `REFUTED`, a non-exploitability conclusion, an application-wide conclusion, or a fixed-source conclusion.

## Immutable scoring boundary

Assessment scoring accepts only the exact final record committed as `result.{run_id}`. It reconciles that immutable reference, loads and normalizes the saved result, and requires it to match the supplied final result before revalidating saved evidence. The CLI follows the same path: after loading a committed result it restores the reconciled artifact reference for scoring. There is no separate scoring ledger.

A scorer accepts `DEMONSTRATED` only when a saved expected operation validates. For `NOT_DEMONSTRATED`, every retained round must be a valid held pair with consecutive expected operation IDs (`{run_id}.r1`, `{run_id}.r2`, and so on); a truncated or copied record fails. This is in addition to the completed execution and oracle checks.

## Candidate language cohorts

Node and Java datasets are separate from each other and from preserved Python cohorts. The only current candidate ABIs are the `.mjs` ESM/JSON Node recipe and the static Java `String`/`String` recipe. Their checked-in native observers use Node `node:test` JUnit/LCOV reporting and a pinned JDK/JUnit Platform/JaCoCo/Jackson observer respectively. Current native and full qualification conclusions remain in [PLAN-0127](../plans/archive/plans/PLAN-0127-outcomes-node-java.md), not in schema or image presence.

## Running a composed question

Run only with deliberately selected settings and reviewed prerequisites:

```bash
BATCH_ID="evaluation-$(date +%s)"
uv run --locked --extra providers corsair eval evals/datasets/dev.json \
  --run-id "$BATCH_ID" --repeats 3 --concurrency 2 \
  --output ".runs/evaluations/${BATCH_ID}.json" \
  --settings /operator/settings.json
```

This command is an execution surface, not a result. Preserve the full denominator—matches, mismatches, abstentions, malformed outputs, provider/configuration failures, unavailable rows, unexpected exceptions, invalid evidence, incomplete assessments, and uncertain operations. See [testing](../development/testing.md), [extensions](../guides/extensions.md), and the [baseline policy](../../evals/baselines/README.md) for required separation.
