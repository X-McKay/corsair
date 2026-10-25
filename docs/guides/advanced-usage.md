# Advanced usage

Use advanced operations to compare bounded runs and recover their real state—not to manufacture a negative security clearance. Corsair records immutable evidence/result artifacts and exposes native Temporal status, but an unavailable or uncertain operation remains unavailable or uncertain.

## Run a finite repeated batch

A dataset evaluation creates one bounded Temporal batch and finite child investigations. Repeats and concurrency are explicit:

```bash
uv run --locked --extra providers corsair eval \
  evals/datasets/dev.json \
  --repeats 3 --concurrency 2 \
  --output .runs/evaluations/dev.json \
  --settings .state/settings.json
```

`--repeats` defaults to `1` and `--concurrency` to `2`. The typed batch contract permits at most 64 requests, 8 repeats, 8 concurrent child workflows, and a 1 MB serialized batch; split larger work into deliberately named finite batches. The evaluator's oracles remain outside the workflow and agent inputs. `eval` waits for actual child results, scores committed artifacts, writes the explicit report path (or `.runs/evaluations/<batch-id>.json`), and exits nonzero if rows fail or results are unavailable.

Use a unique `--run-id` when you need a stable batch identity. Its child IDs are derived as `<batch-id>.c<case-index>.r<repeat-index>`, so do not reuse the batch ID for changed input. Inspect actual batch completion rather than inferring progress:

```bash
corsair inspect "$BATCH_ID" --online --settings .state/settings.json
corsair inspect "$BATCH_ID" --online --watch --settings .state/settings.json
```

Online batch status reports completed and total child work. It is not a quality metric or a guessed percentage.

## Rescore saved evidence without rerunning work

To apply the current evaluator scoring to already committed result artifacts, name the original dataset and saved run IDs:

```bash
corsair rescore evals/datasets/dev.json RUN_ID_ONE RUN_ID_TWO \
  --output .runs/evaluations/rescored.json \
  --settings .state/settings.json

corsair report .runs/evaluations/rescored.json
```

`rescore` reads committed artifacts and evaluator-owned oracles locally. It does not submit a workflow, call a model, contact Temporal, regenerate evidence, or convert an absent artifact into a pass. An unavailable artifact stays an explicit unavailable row. `report` only summarizes a saved report; it does not rescore or repair it.

## Cancel, reconnect, and recover honestly

Client interruption during `investigate --wait` or `inspect --online --watch` detaches that client only. It does not cancel the remote workflow. Start with a live query, then wait only when this client should remain attached:

```bash
corsair inspect "$RUN_ID" --online --settings .state/settings.json
corsair inspect "$RUN_ID" --online --watch --settings .state/settings.json
```

Request cancellation explicitly, then confirm the final workflow state and committed artifact separately:

```bash
corsair cancel "$RUN_ID" --settings .state/settings.json
corsair inspect "$RUN_ID" --online --watch --settings .state/settings.json
corsair inspect "$RUN_ID" --settings .state/settings.json
```

A cancellation request is not proof that a Docker operation stopped or cleaned up. The offline `inspect` form reads a committed result from the configured artifact root; it cannot recover an artifact missing after host loss. Preserve the run ID, container/resource receipts, and any operation intent while restoring the artifact store or service dependency.

## Do not hide retries or uncertainty

Durable investigation rounds are limited by the request budget: rounds, model/tool calls, output tokens, probe timeout, and elapsed time. Producer, auditor, native evidence, and preparation activities use a single Temporal attempt. The provider path also reports failures as bounded episode data and LiteLLM is configured with zero retries. The only special case is final result recording: it is idempotent and may receive up to three attempts inside its own 90-second schedule-to-close window.

Therefore, do not add a wrapper that silently retries a provider call, resubmits an uncertain native operation, deletes an intent, reuses an ID, or treats a missing cleanup receipt as success. Create a new, explicit run only after recording why the prior operation was uncertain. `verify` is useful for native reference observation, but it never emits a release-facing disposition.

A held control/adversarial property is an observation, not a universal fix claim. `INCONCLUSIVE`, `ERROR`, `BLOCKED`, and `CANCELLED` are operationally and evidentially distinct; none authorizes a negative clearance. The current live native batch is partial (2/3): the safe case's second round reached an execution error and correctly ended `ERROR`/`INCONCLUSIVE`, rather than a successful negative finding. The isolated producer and auditor freezes passed 3/3 and 6/6 respectively, and 134 Mac qualification tests passed, but those small fixtures do not establish population accuracy; the current local Linux revision was not rerun. See [ISSUE-0010](../plans/active/ISSUE-0010-live-safe-case-probe.md) for the attributable record.

For complete CLI behavior and exit statuses, use the [CLI reference](../reference/cli.md). For active limitations and planned work, see the [current plans](../plans/README.md).
