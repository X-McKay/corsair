# Run record schema `corsair-v2-run/1`

Every v2 run (direct and Temporal) writes one directory, `<run_root>/<run_id>/`, through `record.RunRecorder`.
`run.json` and `summary.json` carry `"schema": "corsair-v2-run/1"`. Change the version when a field is removed,
renamed or changes meaning; adding a field keeps it.

**Null means unknown, never zero.** A value the provider, Docker or git did not report is `null`. A sum over
values with one `null` is `null`. A known zero (no agent calls, no retries in a captured history) is `0`.

Compare runs with `corsair-v2 runs compare <run_dir> [<run_dir> ...]` (one line per run).

Use `--format json` for one versioned `corsair-v2-cli/1` stdout object, preserving JSON nulls;
`--agents` adds recorded per-agent telemetry to text comparison. Missing/malformed record directories
return exit 2 rather than an all-unknown success row. An unfinished file only proves an **incomplete**
record, never that a process or remote workflow is still running.
Client cancellation emits one JSON object and exit 130: `verdict` is null, `totals` is null when no
summary exists, and `client_interrupted: true` does not claim a remote workflow or command stopped.
Its `state` comes only from the persisted receipt (direct cancellation: `cancelled`).

**Comparison compatibility change:** older `runs compare` returned success with `-` columns for an
absent run directory. It now returns **exit 2**, prints a diagnostic to stderr and emits no success
output if any directory is missing, empty or malformed. Scripts should handle exit 2 or filter for
actual recorded directories before comparison; valid legacy records remain readable with unknown fields.

Stage dispatches update `last_started_step` through that operation's recorder, not the progress callback.
In Temporal mode the worker opens only the request's shared `run_dir`; the display callback never chooses
or creates a run directory. This does not change the shared-filesystem requirement or prove remote cleanup.

## `run.json`: what produced the run

| field | type | meaning |
|---|---|---|
| `schema` | str | `corsair-v2-run/1` |
| `run_id`, `case_id` | str | run directory name; the case's opaque id |
| `mode` | `direct` \| `temporal` | how the chain ran |
| `hostname` | str | host that began the run (Temporal: the control worker) |
| `started_at`, `finished_at` | str \| null | UTC ISO-8601 with `Z`; `finished_at` null until the verdict is written |
| `state` | str | additive lifecycle receipt: `recorded`, `completed` or direct-call `cancelled`; not proof of active work |
| `stopped_at`, `last_started_step` | str \| null | direct cancellation time and last observed stage dispatch; cancellation does not prove external command termination or cleanup |
| `git_commit` | str \| null | HEAD of the checkout the code ran from |
| `git_dirty` | bool \| null | that checkout had changes, untracked files included |
| `provider_config_sha256` | str \| null | sha256 of the provider config file the models were built from |
| `matrix_sha256` | str \| null | sha256 of the runtime matrix file |
| `runtime_row`, `runtime_image` | str \| null | selected matrix row id and its image reference |
| `runtime_image_id` | str \| null | local image id (`sha256:...`, `docker image inspect`) of `runtime_image` |
| `revision`, `fixed_revision` | {`tree_sha256`, `commit`} \| null | the case's trees; `commit` null for a snapshot |
| `environments` | {revision: env} | per revision (`vulnerable`, `fixed`), the replayed environment: `image` (local tag), `image_id`, `tree_sha256`, `recipe_sha256`, `runtime_row` |

## `usage.json`: one row per agent call, in order

`step` plus every `contracts.AgentUsage` field. Parameters are read from the native objects (the model's
`settings` under the agent's own model settings, the `UsageLimits` passed, the agent's retry settings) and the
agent's `agents/<name>/agent.yaml`.

| field | type | meaning |
|---|---|---|
| `step`, `agent` | str | chain step (`investigate`, `probe.control.r1`, ...) and agent name; a second exploit attempt's steps end in `.a2` (`probe-exploit.a2`, `probe.exploit.r1.a2`) or read `review.a2.<n>` |
| `model` | str \| null | model id |
| `provider_host` | str \| null | endpoint host only (no scheme, credentials, path or query) |
| `temperature`, `max_tokens` | float/int \| null | null when the request does not set it (server default) |
| `thinking` | str \| null | `disabled`, `budget`, `server_default` (settings carry no thinking control) or the native `thinking` setting |
| `thinking_budget` | int \| null | thinking token budget sent, if any |
| `request_limit`, `tool_calls_limit` | int \| null | the run's `UsageLimits` |
| `max_output_retries`, `max_tool_retries` | int \| null | the agent's retry settings |
| `prompt_version`, `config_version` | str \| null | from `agent.yaml` metadata |
| `spec_sha256` | str \| null | sha256 of the agent's `agent.yaml` |
| `wall_s` | float \| null | wall time of the call |
| `requests`, `input_tokens`, `output_tokens`, `tool_calls` | int \| null | native `RunUsage`; tokens null when the provider reported none |
| `retries` | int \| null | retry prompts (`RetryPromptPart`: invalid output or failed tool call) in the run's message history; null when no history was captured |
| `status` | str | `ok`, `output_invalid`, `budget_exhausted`, `provider_error`, `infra_error` |
| `error` | str \| null | upstream failure detail |

## `summary.json`: outcome and cost

| field | type | meaning |
|---|---|---|
| `schema`, `run_id`, `case_id`, `mode` | str | as in `run.json` |
| `label`, `rule_id`, `terminal_reason`, `finding`, `fix` | str | the verdict (kept at top level for older readers) |
| `sensitivity` | `unverified` \| null | on every R5 (LIKELY_NOT_EXPLOITABLE, SPEC-0082 D18): how often a failed PoV pair misses a real vulnerability is not yet measured; null otherwise. Never changes the label |
| `outcome` | object | `label`, `rule_id`, `terminal_reason`, `finding`, `fix`, `fix_reason` (str \| null) and `probes`: {revision: {role: {`outcome`, `facts` (`ProbeFacts`), `duration_s`, `patch_sha256`, `image_digest`, `tree_sha256`, `cleanup_confirmed`}}}, for the pair the rule decided on (after a second attempt: its own runs plus attempt 1's vulnerable control run, which it reuses) |
| `review` | object | attempt 1's review loop: `rounds` and per author (`control`, `exploit`): `first_review_valid`, `revisions_used`, `final_valid`, `recovered` |
| `attempts` | [object] | one per exploit attempt (D18; a second runs only when the first PoV was `assertion_failed` after a positive review): `number` (1 or 2), `patch_sha256` (its final pair; null when none was frozen), `exploit_outcome` (its vulnerable PoV outcome; null when not run), `review_rounds`, `first_review_valid` ({role: bool}), `revisions`, `mechanical_fixes` ({role: int}) and `decided` (the rule read this attempt) |
| `models` | [str] | distinct model ids used |
| `agents` | {agent: object} | per agent, in first-call order: `calls`, `steps`, `models`, `prompt_versions`, `requests`, `input_tokens`, `output_tokens`, `tool_calls`, `retries`, `wall_s`, `statuses` ({status: count}) |
| `totals` | object | `agent_calls`, `requests`, `input_tokens`, `output_tokens`, `tokens`, `tool_calls`, `retries`, `agent_wall_s`, `wall_s` (run start to finish) |

## Other files

`case.json` (the Case), `verdict.json` (the Verdict, with `attempts`, the deciding `attempt` and `sensitivity`;
each `ProbeRun` carries `image_digest`, the image id its container ran from, and `tree_sha256`, the environment's tree; Decide drops a run whose tree is not the case
revision it claims), `timings.json` (per-stage wall time), `stages/<step>.json`, `agents/<step>.messages.json`
(native message history) and `grounding.json`.
