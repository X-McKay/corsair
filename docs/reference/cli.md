# CLI reference

Corsair has one CLI for native reference replay, Temporal-backed investigations, inspection, evaluation, and operational checks. The CLI is deliberately a thin adapter over the Docker and Temporal SDK paths; it does not introduce a second scheduler, agent loop, retry layer, or synthetic progress model.

## Invocation and global switches

```text
corsair [GLOBAL OPTIONS] COMMAND [COMMAND OPTIONS] [GLOBAL OPTIONS]
```

The global switches are accepted before **or** after the command. This makes interactive use and wrappers equally unambiguous.

```bash
corsair --format human --no-animation doctor --settings .state/settings.json
corsair doctor --format human --no-animation --settings .state/settings.json
```

| Switch | Values / argument | Effect |
| --- | --- | --- |
| `--settings PATH` | Settings JSON | Selects the Docker, artifact, Temporal, and model configuration. Credentials remain in the worker environment. |
| `--format MODE` | `auto`, `human`, `json`, `markdown` | Selects command-result output. `auto` is human on a TTY and JSON when stdout is not a TTY. `markdown` writes a GitHub-flavoured Markdown record of a `report`, `compare`, `eval` or `rescore` result (see [`report`](#report-reportjson)); any other command's JSON receipt is written unchanged inside a fenced `json` block. |
| `--no-color` | none | Disables terminal colour in human output. It has no effect on JSON. |
| `--no-animation` | none | Disables the human-terminal spinner/watch animation. It has no effect on JSON. |
| `--log-format FORMAT` | `text`, `json` | Selects stderr log encoding. The optional file mirror is always structured JSON Lines. |
| `--log-level LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | Sets the minimum operational log level. |
| `--log-file PATH` | File path | Mirrors the same sanitized log events sent to stderr into `PATH`. |

`--format json` guarantees that **stdout contains JSON only**. Human panels, spinners, and logs never share that stream. This is the recommended form for pipes:

```bash
set -o pipefail
corsair --format json doctor --settings .state/settings.json | python -m json.tool
```

In human mode, the CLI uses compact Rich output when the terminal supports it. `--no-color` and `--no-animation` are for accessibility, plain terminal recordings, and stable operator transcripts—not a different execution mode.

## Result and log confidentiality

A completed human investigation rendering leads with the canonical verdict, coloured by meaning (red: exploit demonstrated, green: exploit not demonstrated, yellow: inconclusive, magenta: unable to run or error), followed by the case stop, execution status, disposition, scope, fix status, the result reason and run/case identity. A rounds table then lists, per session and round, the producer's decision kind (proposal, abstained or no decision), the gate name that stopped or redirected it, its LLM/tool calls and tokens, the control and adversarial outcomes with their covered target lines, the audit decision with its rule name, and **Stopped at**: the round's [gate-ledger](../agents/evaluations.md) stage and gate. The **case stop** names the case-level policy stops (`budget_exhausted`, `negative_threshold_unmet`, `fix_not_blocked`, `execution_*`), or else the last round's gate with its stage and session.round. Both come from the evaluator's pure [`gate_ledger`](../../src/corsair/evaluation/ledger.py), which describes the recorded verdict and never decides one; only gate and stage names are shown, plus the fixed sentence of a budget, threshold or fix stop, never a ledger reason that can carry model text. A fixed-revision observation, when present, gets its own role table. A **Phases** table follows when the result recorded a timeline: each phase transition's session.round, offset from the first retained transition and duration until the next one (the final `record` has no recorded end, so it shows `-`), with per-phase totals; an unknown time stays `unknown`, and a timeline whose first entry is not `prepare` says that earlier transitions were not retained. The last panel shows the manifest identity (package, abbreviated image and prompt/config digests, models, evidence policy), the full result SHA-256 and the usage totals; missing usage and cost stay `unknown`.

It never shows payloads, the hypothesis or plan, the auditor's reason, feedback reasons (which can carry model text) or any oracle data. Values are rendered as plain text, never as Rich markup, and long values wrap instead of being cut. It does not invent an intermediate stage or claim unobserved work. JSON output remains the complete record; its only addition is the result's `timeline` field (see [`inspect`](#inspect-run_id)).

```text
╭────────────────────────── Corsair · Investigation ───────────────────────────╮
│ Verdict      EXPLOIT_DEMONSTRATED                                            │
│ Case stop    demonstrated · kernel at 1.1                                    │
│ Execution    COMPLETED                                                       │
│ Disposition  SUPPORTED                                                       │
│ Scope        component                                                       │
│ Fix          NOT_REQUESTED                                                   │
│ Reason       paired native observation supports the component claim          │
│ Run          run1                                                            │
│ Case         case01                                                          │
╰──────────────────────────────────────────────────────────────────────────────╯
Rounds
┏━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ S.R ┃ Producer     ┃ Control    ┃ Adversarial  ┃ Audit        ┃ Stopped at   ┃
┡━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ 1.1 │ proposal     │ held       │ violated     │ ACCEPT       │ demonstrated │
│     │ 3 llm · 4    │ L12-14, 20 │ L12-14,      │ differential │ kernel       │
│     │ tool         │            │ 20-21        │ -is-relevant │              │
│     │ 1200/210 tok │            │              │              │              │
└─────┴──────────────┴────────────┴──────────────┴──────────────┴──────────────┘
Phases
┏━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┓
┃ S.R        ┃ Phase                 ┃ At               ┃ Duration             ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━┩
│ 0.0        │ prepare               │ +00:00           │ 1.8 s                │
│ 1.1        │ producer              │ +00:01           │ 39.5 s               │
│ 1.1        │ evidence              │ +00:41           │ 11.3 s               │
│ 1.1        │ audit                 │ +00:52           │ 5.5 s                │
│ 1.1        │ record                │ +00:58           │ -                    │
└────────────┴───────────────────────┴──────────────────┴──────────────────────┘
totals: prepare 1.8 s · producer 39.5 s · evidence 11.3 s · audit 5.5 s
╭───────────────────────────── Identity · Totals ──────────────────────────────╮
│ ...                                                                          │
╰──────────────────────────────────────────────────────────────────────────────╯
```

The example uses synthetic digests and model names.

Structured JSON logs use a metadata allowlist: for example, timestamp, level, run/workflow identity, workflow phase/round, event name, and safe exception classification. They must not serialize prompts, source excerpts, source trees, payloads, secrets, provider responses, or raw model reasoning. Before exception text is emitted, configured endpoint URLs and known credential values from the environment are redacted. Text logs follow the same content boundary. Raw SDK content is suppressed because it can carry request data; the safe event retains the originating logger, severity and available exception class. Pydantic validation diagnostics identify failed fields without reflecting rejected values. With `--log-format json`, expected CLI errors are emitted as JSON Lines diagnostics rather than as a second plaintext error line. A failed command logs `cli.failed` with `error_type` and the sanitized `message`; when the failure belongs to a known class (missing file, invalid settings or JSON, source admission, Docker daemon or image, Temporal connection, namespace or run identity, missing committed result) it also carries a `remedy`, printed on its own `remedy:` line in text logs and as a `remedy` field in JSON logs. Remedies are fixed text chosen in [`terminal.py`](../../src/corsair/entrypoints/terminal.py); they never echo the error, and an unrecognized failure has no remedy rather than a guessed one.

A log file mirrors the same sanitized events as structured JSON Lines, even when stderr uses the text formatter. New files use mode 0600; existing file permissions remain the operator’s responsibility. Console logging is configured before file I/O, so a bad mirror path still emits a safe JSONL failure when JSON logs are selected. It is not an evidence or result artifact. Keep it restricted: safe metadata can still identify runs, schedules, local paths, and operational timing. Do not put logs, private `.runs` data, credentials, or raw provider output in source control.

## Commands

### `doctor`

```bash
corsair doctor --format human --settings .state/settings.json
corsair --format json doctor --settings .state/settings.json
```

`doctor` is an operational preflight, not a security or provider qualification. It checks the configured values against live/local dependencies:

- settings can be read and the configured source and artifact directories are usable;
- the Docker daemon is reachable, the configured image resolves, and the configured runtime is available to Docker;
- the configured Temporal address and namespace are reachable; and
- the configured task queue has worker pollers.

By default it makes no model request and does not validate provider credentials, model availability, prompt policy, or a future investigation’s likely result. It does not build an image, create directories, start a worker, change Docker/Temporal state, or submit a workflow. It does not create or modify source content.

```bash
corsair doctor --model --format human --settings .state/settings.json
```

`--model` adds provider-route checks after the infrastructure checks. It sends no agent prompt, source, finding, or Corsair packet; the probes are short fixed sentences, sent through the same ADK model object each role uses (`model_for_role`; a plain Gemini id resolves through ADK's model registry, as an agent does):

| Check | What it reports |
| --- | --- |
| `model_config` | Connector, producer and auditor model names, the `api_base` host and port only (never userinfo, path, query, or fragment), `request_timeout_seconds`, and the `extra_body` key names. |
| `model_credentials` | Whether each role's provider credential variable is set, by **name only**; the value is never read into the report. A missing required variable fails; a route with no known variable warns. |
| `model_producer`, `model_auditor` | One non-streaming request per role with a 32-token output cap and no tools: latency, finish reason, and reported output tokens. Stopping at the probe cap still passes, because the route answered; reasoning tokens count against the cap, and role caps are separate. |
| `model_producer_tools` | One request on the producer model declaring a single argument-free tool, with a 128-token cap. It passes only when the response is a native call of that tool. When the model declares that it supports a response schema alongside tools, the probe pairs a trivial schema with the tool, as the producer's requests do. A text answer fails (the route would void every producer episode); stopping at the cap without a call is an inconclusive `warn`. |

Credential variables follow the connector's conventions: `gemini` needs `GOOGLE_API_KEY` or `GEMINI_API_KEY` (or `GOOGLE_CLOUD_PROJECT` when `GOOGLE_GENAI_USE_VERTEXAI` is `true`); `litellm` routes map by model prefix: `openai/` to `OPENAI_API_KEY`, `anthropic/` to `ANTHROPIC_API_KEY`, `gemini/` to `GEMINI_API_KEY` or `GOOGLE_API_KEY`, `openrouter/`, `groq/`, `mistral/`, `deepseek/`, `xai/` to their `PREFIX_API_KEY`, `together_ai/` to `TOGETHERAI_API_KEY`; `hosted_vllm/` (`HOSTED_VLLM_API_KEY`) and `litellm_proxy/` (`LITELLM_PROXY_API_KEY`) are optional, and `ollama/` needs none. The mapping lives in [`diagnostics.py`](../../src/corsair/entrypoints/diagnostics.py).

Each request is bounded by `request_timeout_seconds` plus five seconds, and the three run concurrently. A failed model check carries sanitized detail and, for a known class (timeout, authentication, unknown model, connection, missing providers extra, missing tool call), a fixed `remedy`. A ready `--model` report shows that each route answered a minimal request and that the producer route returns tool calls. It is not a provider qualification: prompt-sized requests, provider policy, role output caps, evidence, and accuracy remain untested, and the requests are billed like any other.

A failed doctor report identifies the failed dependency, adds the same fixed `remedy` to a failed check of a known class, and exits nonzero. A missing workflow or activity task-queue poller is reported as a warning check, but the overall report is not ready and exits `1`. Resolve the dependency rather than bypassing the check or substituting fake health data.

### `worker`

```bash
corsair worker --settings .state/settings.json \
  --log-level INFO --log-file .state/worker.log
```

Starts the configured Temporal SDK worker for the investigation and evaluation task queues. Provider credentials are read only from the worker environment. The client process that submits or inspects work does not receive them through a request, artifact, or CLI option.

The worker uses the SDK worker context and a 45-second graceful-shutdown timeout. On `SIGTERM`, it stops accepting work and lets the SDK drain/cleanly shut down within that bound. Treat an interrupt or host loss as an operational event: inspect the resulting workflow and immutable artifacts rather than assuming all native side effects completed.

### `verify REQUEST SUBMISSION`

```bash
corsair verify evals/fixtures/case01/request.json \
  evals/fixtures/case01/submission.json \
  --settings .state/settings.json

# Test the request's declared fixed source as a separate native observation.
corsair verify evals/fixtures/case01/request.json \
  evals/fixtures/case01/submission.json --fixed \
  --settings .state/settings.json
```

Runs the trusted native reference observer directly against an admitted request/submission pair. It requires Docker and the configured image; it does not contact Temporal or a model. It returns observation data, never a release-facing security disposition. Use this first when bringing up a host or changing source-admission, driver, image, or runtime behavior.

In human mode the observation is shown as a header (explicitly "no security verdict", operation identity, abbreviated source and submission digests, cleanup confirmation, any kernel gate with its reason, and the evidence SHA-256) and a role table with each role's outcome, whether the target ran, the native exit code, covered target lines and the kernel's role reason. It never shows the submitted payloads.

`--run-id ID` optionally supplies the operation identity. A healthy control/adversarial execution exits `0`, whether it demonstrates a violation or not; an invalid or operational native observation exits `1`.

### `investigate REQUEST`

```bash
RUN_ID="case01-$(date +%s)"
corsair investigate evals/fixtures/case01/request.json \
  --run-id "$RUN_ID" --wait --settings .state/settings.json
```

Starts a `corsair.investigation` Temporal workflow under a unique run ID. The workflow uses the configured task queue and writes immutable result/evidence artifacts to the shared artifact root.

Without `--wait`, the command returns submission identity after Temporal accepts the workflow. With `--wait`, it waits for the actual workflow result and displays the completed panel or JSON result. Ctrl-C while waiting detaches the local client; it does **not** cancel the remote workflow. Use `corsair cancel` if cancellation is intended.

The client connects through the Temporal SDK to the configured address and namespace. It does not add an application-level retry policy around SDK connection or workflow operations; outcomes and failures remain visible to the operator.

### `inspect RUN_ID`

```bash
# Committed result from the shared artifact store.
corsair inspect "$RUN_ID" --settings .state/settings.json

# Live Temporal workflow query.
corsair inspect "$RUN_ID" --online --settings .state/settings.json

# Query live status and wait for the actual final workflow result.
corsair inspect "$RUN_ID" --online --watch --settings .state/settings.json

# Per-role native receipts behind the committed result.
corsair inspect "$RUN_ID" --evidence --settings .state/settings.json
```

Without `--online`, `inspect` reads the immutable committed result from the shared artifact store. It cannot recover a result if the artifact root is unavailable or the workflow has not recorded one. In human mode it renders the result with its gate ledger verified: each round that reached the kernel is classified from that round's own committed receipts, revalidated with the trusted verifier's admission rules, so **Stopped at** names the kernel or audit gate (`demonstrated`, `clean_negative`, `coverage`, `audit_reject`, ...). A round whose receipts do not validate shows `evidence_unverified`, never a gate read from unverified fields. The same view after `investigate --wait` verifies against the local artifact root only when it already exists; otherwise, and after `inspect --online --watch`, which never opens a local store, kernel rounds show `evidence_unverified` with a caption saying so. The verdict shown is always the recorded one.

The result's `timeline` (in JSON too) is the workflow's bounded phase timeline, recorded at finalization: up to the last 32 transitions, each with `phase`, `session`, `round` and the deterministic workflow time `at`. It is the same data the live status query reports, persisted so durations can be read after the workflow has closed; it is presentation metadata and never an input to a verdict. Results recorded before the field existed read as an empty timeline, and the Phases table is then omitted. JSON output is otherwise unchanged: the ledger is computed for display only and is not added to the result.

With `--online`, it uses the workflow’s native status query without opening or creating a local artifact store. `--watch` without `--online` is rejected before runtime I/O. For an investigation, the reported phase and round come from the actual Temporal workflow state, not a CLI estimate. For an evaluation, the status reports actual completed and total child work and a bounded per-child state list. `--watch` repeats the native status query while the workflow remains open, then waits for and returns the workflow’s actual final result. It does not fabricate a percentage, infer model progress, or turn an activity heartbeat into a security conclusion.

`--evidence` reads the committed result offline (it is rejected with `--online`) and walks each round's observation, and the fixed-revision observation when present, to its committed operation record, evidence bundle and raw container receipts. Each observation reports `committed` (the operation record resolves to the same observation the result carries), `evidence` (`present`, `absent` or `unreadable`), `cleanup_confirmed`, the feedback `gate`, and `receipts_admissible`: whether the saved receipts still pass the trusted verifier's admission rules, or `null` when the round has no submission or the result has no manifest. When the receipts are admissible it also reports, from the verified prepared case, `target_line` (the line the coverage gate checked, after line binding), `declared_line` (the finding's line it was bound from) and `line_provenance` (`declared`, or `recipe_function` when prepare derived the line from the recipe function); all three are `null` otherwise. The human caption shows them in one phrase, for example `target=L5 (declared L4, bound to its reported statement)`. Per role it reports the admitted `outcome`, `target_executed`, `covered_lines` and `native_exit_code`, and from the raw receipt only `receipt` status, `cleanup_confirmed`, `container_id`, `image_id`, `docker_exit_code` and the receipt digest. Payloads, the driver job and record, the rest of the prepared case (finding text, recipe and source excerpt) and model output are never printed. The view is a navigation aid, not a verdict: the label remains the result's code-decided `verdict`, and `receipts_admissible: false` is an operational fact to investigate, never a negative security result.

### `runs`

```bash
corsair runs --settings .state/settings.json
corsair runs --case case01 --limit 5 --settings .state/settings.json
corsair --format json runs --settings .state/settings.json | jq -r '.runs[].run_id'
```

Lists committed investigation results in the artifact store, newest first, without contacting Temporal, Docker or a model. Each row has `run_id`, `case_id`, `verdict`, `execution_status`, `fix_status`, `rounds`, `recorded_at` and `result_sha256`. `--case ID` keeps only that case; `--limit N` (at least 1) caps the rows after filtering.

Operation names are stored hashed, so the listing reads every committed record and admits a result only if it validates and is committed under its own `result.<run_id>` name. Observation and intent records are skipped. `invalid_records` counts records that could not be read or a result-shaped record that failed validation or that binding; they are reported, never listed or repaired. `recorded_at` is the operation record's filesystem time in UTC: operational metadata for ordering, not evidence, and it changes if the store is copied without preserving times. The command never writes to the store, although opening an absent artifact root creates its empty directories as every local store command does.


#### Live progress while waiting

`investigate --wait`, `inspect --online --watch` and `eval` poll the workflow's native `status` query about once a second and render it on stderr; stdout still carries only the final result.

| Field | Investigation query | Evaluation query |
| --- | --- | --- |
| Position | `phase`, `session`, `round` | `completed`, `total` |
| Bounds | `max_sessions` (admitted manifest; `0` before prepare), `max_rounds` (budget) | `running` (child workflows in flight), `errors` (child workflows that failed) |
| Time | `started`, `deadline` (ISO 8601 workflow time; the deadline is the elapsed-time budget) | `started` (when the batch began, workflow time) |
| Kernel | `gate`: the last feedback gate name (for example `retry`, `audit`, `producer`), or `null` | none |
| History | `timeline`: the most recent 32 phase transitions, each `{phase, session, round, at}` | `children`: at most 64 rows `{case_id, repeat, run_id, state, started, finished}`, ordered running, failed, pending, completed, then by case and repeat; `children_omitted` counts rows past the cap |

The query carries workflow-owned metadata only: no model text, feedback reason, source, payload, observation or label. A child's `state` is `pending` (waiting for a concurrency slot), `running` (its investigation workflow started), `completed` (it returned a result, whatever the verdict) or `failed` (the child workflow itself failed, counted in `errors`); `started` and `finished` are the parent's workflow time at those transitions. A running child's own phase and round are not in the parent's state, so the evaluation view does not show them; use `inspect RUN_ID --online` on the child's `run_id`. The view adds only local wall-clock time (elapsed since `started`, time left before `deadline`, a running child's time so far).

- Human mode on an interactive terminal draws a live panel: the current phase with a spinner, elapsed time, session n/max, round n/max, last gate, deadline with time left, and the last eight transitions with their offsets from the start. An evaluation shows completed/total cases, running, errors, a progress bar of completed over total, and a table of the first 16 child rows (state, case, repeat, elapsed, run id) with a `… N more` row for the rest.
- Human mode with `--no-animation`, or when stderr is not a terminal, prints one plain line per status change and no cursor movement. For an evaluation that is one line per child state change (the batch counts followed by the case, repeat, new state and that child's elapsed time); a child first seen pending prints nothing.
- `--format json` prints no progress view; progress is visible only as `workflow.progress` log events.

A failed query is logged once as `workflow.progress_unavailable` and the view keeps the last real status; it never invents progress.

### `cancel RUN_ID`

```bash
corsair cancel "$RUN_ID" --settings .state/settings.json
```

Requests cancellation through Temporal. A cancellation request is not proof that owned Docker resources have already stopped or been removed. Follow it with `inspect RUN_ID --online --watch` and then offline `inspect RUN_ID`; retain the result and resource receipts before claiming cleanup.

### `eval DATASET`

```bash
corsair eval evals/datasets/dev.json --repeats 3 --concurrency 2 \
  --output .runs/evaluations/dev.json --settings .state/settings.json
```

Starts a bounded Temporal evaluation batch. The evaluator-owned oracle labels do not enter request, agent, or child-workflow inputs. Once the actual child results are available, the CLI scores their committed artifacts and writes the report.

`--run-id ID`, `--repeats N`, and `--concurrency N` select the finite batch. `--output PATH` remains the explicit report path; if omitted, the default is `.runs/evaluations/<batch-id>.json`. An evaluation returns nonzero when the completed report has failed rows or unavailable results. Query its live complete/total count with `inspect BATCH_ID --online` (and add `--watch` to wait).

### `dataset validate DATASET...`

```bash
corsair dataset validate evals/datasets/dev.json evals/datasets/producer-dev.json
corsair --format json dataset validate evals/datasets/safety.json
corsair dataset validate evals/datasets/dev.json --fix-digests
```

Checks frozen dataset manifests offline before an `eval`, `eval-agent` or `rescore` spends a model, container or service on them. It runs no model, target code, container or Temporal request and writes nothing except, with `--fix-digests`, the manifest. Both manifest schemas are accepted: composed-case datasets (`corsair.dataset/1`) and isolated producer/auditor datasets (`corsair.agent-dataset/1`, the role inferred from each input). For every entry it runs these checks over the exact bytes the evaluator reads:

| Check | What fails it |
| --- | --- |
| `entry` | Malformed entry, duplicate `case_id`, a `family` or `split` that is not a lowercase identifier, or a family that crosses splits. |
| `digests` | A request/input or oracle path that is missing or escapes the dataset root, or a declared `*_digest` that differs from the file. |
| `request` | The request (or auditor input) fails its contract, or the request's `case_id` differs from the entry. |
| `source` | The source or fixed source has no `expected_digest`, cannot be admitted, or its snapshot digest differs; the fixed source lacks the recipe module. |
| `target_binding` | The pure pre-model [`target_binding`](../../src/corsair/policies/target_binding.py) gate blocks the case and the oracle does not accept the resulting `UNABLE_TO_RUN`/`BLOCKED` result (the case could never pass). A block the oracle does expect passes with a note. |
| `oracle` | A case oracle lists a disposition or verdict as both acceptable and forbidden, has an empty `acceptable_verdicts`, an `expected_verdict` outside `acceptable_verdicts` or inside `forbidden_verdicts`, or no satisfiable verdict; a producer oracle has no candidates or lists its control as a candidate; an auditor oracle names an unknown decision, or a `rule` its decision does not allow (`ALL` for `ACCEPT`, `R1` to `R4` otherwise). |

A check that cannot run because an earlier one failed is `skip`, as are source and target binding for auditor entries. After the entries, the consuming evaluator's own loader (`load_dataset`, or the isolated fixture loader) is run so its rules cannot drift from these checks. When several datasets are given, a family placed in different splits by different manifests is reported too. Human output shows each dataset's schema, role, dataset digest (the `dataset_digest` an evaluation report of it records) and cohort, a table of check results per entry, then each problem; `--format json` emits the complete record. Problems name fields and labels but never an oracle payload. Sources are admitted below the dataset root by default; pass `--settings` to admit them under that file's `source_root` and limits instead, as the worker will.

`--fix-digests` rewrites only stale `request_digest`, `input_digest` or `oracle_digest` values in the manifest, and only for entries whose every other check passes; it never edits a request, input, oracle or source, nor a request's own source `expected_digest`. Each change is listed with its old and new digest and whether it was applied, and the datasets are validated again afterwards. A rewritten digest changes the dataset digest, so it is a new frozen cohort identity: treat it as the deliberate, reviewed change [evaluation discipline](../development/testing.md#frozen-inputs-and-evaluation-discipline) requires, never as a way to turn a failed run green.

The command exits `0` when every dataset is valid and `1` when any entry, manifest or cross-dataset check fails.

### `rescore DATASET RUN_ID...`

```bash
corsair rescore evals/datasets/dev.json run-a run-b \
  --output .runs/evaluations/rescored.json --settings .state/settings.json
```

Scores existing committed result artifacts against evaluator-owned oracles without starting model or Temporal work. `--output PATH` is retained and defaults to `.runs/evaluations/rescored.json`.

### `report REPORT.json`

```bash
corsair report .runs/evaluations/dev.json
```

Reads an existing evaluation report. Human output shows the summary, the report's dataset digest and one table row per scored attempt (case, run, status, verdict or disposition or match kind, the gate of the row's final [gate ledger](../agents/evaluations.md#reading-results) entry, usage and reason); unknown usage is shown as `unknown`. `--format json` emits the complete saved report (`rows`, `summary` and `dataset_digest`). It does not re-run, re-score, or repair the report.

```bash
corsair --format markdown report .runs/evaluations/dev.json > record.md
```

`--format markdown` writes the same report as a record to paste into a baseline README, a pull request or a plan: the baseline-policy caveats (a candidate diagnostic, not a promoted baseline; unknown usage stays `unknown`; a gate the record does not show as run is unrun, not passed; and, for an all-`live-model-fixture` report, that no target code, Docker, Temporal or full chain ran), an identity table (dataset digest, the distinct `config_digest` values and model names recorded in rows, or `unknown`, plus agent-resources digests, agents and cohorts when rows carry them), the scalar summary, one row per attempt (case, repeat, run, status, label, stopping gate and usage) and the `gate_ledger` and `failure_stops` tables. The stopping gate is the row's final gate-ledger `gate`, or an isolated row's feedback `gate`. Rows never show their `reason`, which can carry an auditor's review or a producer's abstention text, and never payloads. Every cell is sanitized and escaped, so a pipe or newline in a value cannot break a table. The renderer is [`entrypoints/markdown.py`](../../src/corsair/entrypoints/markdown.py): `report_markdown(report)`, `comparison_markdown(comparison)` and the dispatcher `to_markdown(value)` take the JSON-mode result and return text.

### `compare BASELINE.json CANDIDATE.json`

```bash
corsair compare .runs/evaluations/before.json .runs/evaluations/after.json
corsair --format json compare .runs/evaluations/before.json .runs/evaluations/after.json
```

Compares two saved evaluation reports without contacting services or re-scoring. Rows join on `(case_id, repeat)`: an isolated report's own `repeat` field, otherwise the row's position among that case's rows, which follows the batch's case-major, repeat-minor order. For every joined attempt it reports the status flip (`pass_to_fail` or `fail_to_pass`; an `unavailable` row is not a pass), a verdict/label change, a newly forbidden label, and usage deltas for LLM calls, tool calls, input/output tokens and agent seconds. Summary deltas are recomputed from each report's rows. A delta with an unknown side stays unknown, never zero. `gate_delta` lists, for `gate_ledger` and `failure_stops`, each gate's baseline count, candidate count and delta (moved gates first), and each joined attempt carries `baseline_stop`/`candidate_stop`, the gate of its final ledger entry; isolated rows saved without a ledger derive it from their match kind and feedback. Gate movement attributes a change and never decides a regression. The result also lists each side's dataset digest, config digests and cohorts.

The comparison is refused (exit `2`) when the dataset digests differ or either report does not declare one. `--allow-dataset-mismatch` compares them anyway; the result then carries `dataset_match: false`, the human output opens with a mismatch warning and a `compare.dataset_mismatch` warning is logged. A mismatched comparison is not a statement about one frozen dataset.

The command exits `1` when the candidate regressed: a baseline pass that does not pass in the candidate, a forbidden label the baseline row did not have, a baseline attempt missing from the candidate, or more rows without a case identity than the baseline had. Otherwise it exits `0`, including when cases only improved or were added. Human output opens with a `gates moved` line, renders the per-gate table and lists only attempts whose status, label, forbidden flag or presence changed, with their final stop; `--format json` emits every joined attempt under `cases` along with `regressions`, `counts`, `summary_delta` and `gate_delta`. `--format markdown` writes the result line, the caveats (a dataset mismatch first), an identity table per side (report path, dataset digest, config digests, cohorts), the counts, the summary deltas, the regressions and the changed attempts with their usage deltas; a side an attempt is missing from is `absent`. The exit codes are the same in every format.

## Watching and recovery

A native activity records an immutable intent before its Docker side effect and reconciles a committed observation by identity. A committed observation can be recovered from the artifact root. An intent with no committed observation is uncertain—even if no container remains—and is not safe to replay automatically.

The requested investigation action budget (`max_elapsed_seconds`) is distinct from the final result-recording step. Result recording has a 90-second schedule-to-close bound that includes queueing, retry, and backoff. Its idempotent retry policy preserves a completed result when possible; it does not make a lost host, unavailable artifact store, or unrecorded native operation safe to treat as successful.

Use this sequence after a client disconnect, worker restart, or Ctrl-C:

```bash
# Is the workflow still live? Use --watch only when you want this client to wait.
corsair inspect "$RUN_ID" --online --settings .state/settings.json

# After completion, retrieve the immutable committed result.
corsair inspect "$RUN_ID" --settings .state/settings.json
```

Do not delete an intent to obtain a pass, reuse a run ID with a different request, or blindly rerun an uncertain operation. Preserve the run ID, inspect owned resource identifiers, and record uncertainty. Temporal history alone cannot restore a separate local artifact filesystem after host loss.

## Exit statuses

| Exit | Meaning |
| --- | --- |
| `0` | The command completed its stated healthy/success condition. |
| `1` | A completed doctor, investigation, reference replay, evaluation, scoring, dataset validation, or report comparison operation reported a non-success/unhealthy condition, an invalid dataset or a regression. `runs` and `inspect` never exit `1` on a verdict. |
| `2` | Input, settings, invocation, or local configuration validation failed before normal execution. |
| `130` | Ctrl-C interrupted the local CLI. A remote workflow is not implicitly cancelled. |

Always parse the returned JSON or result panel in addition to the exit code. In particular, the labels `EXPLOIT_DEMONSTRATED`, `COMPONENT_EXPLOIT_DEMONSTRATED`, `EXPLOIT_NOT_DEMONSTRATED`, `INCONCLUSIVE`, `UNABLE_TO_RUN` and `ERROR` and the execution statuses `BLOCKED` and `CANCELLED` have different evidence and operational meanings.

## Troubleshooting

### Docker daemon, image, or runtime is missing

Run `corsair doctor` first. If it reports no reachable Docker daemon, start the host’s Docker service or point the client at the actual rootless socket:

```bash
export DOCKER_HOST="unix:///run/user/$(id -u)/docker.sock"
docker info
```

If the configured image is absent, build the reviewed image rather than changing the investigation to an arbitrary tag:

```bash
just images
docker image inspect corsair-python:0.1
```

If the configured runtime is unavailable, compare `runtime` in the settings file with the daemon’s installed runtimes:

```bash
docker info --format '{{json .Runtimes}}'
```

Install/configure the desired runtime at the Docker daemon, or use the reviewed configured runtime. Do not relax network, resource, or socket-isolation policy to make a check pass.

### Source or artifact directory check fails

Set `source_root` to the narrowest absolute directory that contains the admitted source. Ensure every worker and client uses the same durable `artifact_root`, and that its parent is writable by the operator. `doctor` does not create the root; a command that opens the local artifact store may do so. Neither behavior makes a lost host recoverable.

### Temporal connection, namespace, or poller check fails

For local development, start the service in one terminal:

```bash
temporal server start-dev --db-filename .state/temporal.db
```

Then start a worker using **the same** `temporal_address`, `temporal_namespace`, and `task_queue` from settings:

```bash
corsair worker --settings .state/settings.json
```

Run `corsair doctor --settings .state/settings.json` again. A reachable Temporal service without a task-queue poller means the worker is not connected to the configured queue; it does not mean investigations can run. Do not solve this by submitting work to a different queue without changing and reviewing the operator configuration.

### A watch was interrupted or a result is unavailable

Ctrl-C detaches the CLI. Re-run online inspection to learn the live workflow state, then use offline inspection once the result is recorded. If online inspection fails because Temporal is unavailable, restore Temporal connectivity before drawing conclusions. If offline inspection fails after host loss, recover the shared/backup artifact store; Temporal history is not a substitute for that storage.

## Limits that the CLI cannot diagnose away

`doctor` cannot verify provider credentials, provider policy, or live-model reliability. The original live security-producer request was blocked by provider policy; that block does not establish full live-chain accuracy. Scripted ADK models exist only in labelled tests and are never a production fallback. Do not evade a policy block or silently replace a provider.

The pilot is limited to the supported standard-library Python recipe. Source admission and immutable evidence binding reduce configuration/path confusion; they do not attest arbitrary malicious target/interpreter behavior. The pilot does not provide arbitrary code probes, dependency installation, build repair, other languages, generic negative clearance, application-exposure proof, or hostile-interpreter attestation. See the [pilot runbook](../operations/runbooks/pilot.md) and the packaged [risk assessment](../../src/corsair/policies/risk.md) before use beyond a disposable personal sandbox.
