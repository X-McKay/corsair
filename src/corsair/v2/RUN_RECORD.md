# Run record schema `corsair-v2-run/1`

Every v2 run (direct and Temporal) writes one directory, `<run_root>/<run_id>/`, through `record.RunRecorder`.
`run.json` and `summary.json` carry `"schema": "corsair-v2-run/1"`. Change the version when a field is removed,
renamed or changes meaning; adding a field keeps it.

**Null means unknown, never zero.** A value the provider, Docker or git did not report is `null`. A sum over
values with one `null` is `null`. A known zero (no agent calls, no retries in a captured history) is `0`.

Compare runs with `corsair-v2 runs compare <run_dir> [<run_dir> ...]` (one line per run).

## `run.json`: what produced the run

| field | type | meaning |
|---|---|---|
| `schema` | str | `corsair-v2-run/1` |
| `run_id`, `case_id` | str | run directory name; the case's opaque id |
| `mode` | `direct` \| `temporal` | how the chain ran |
| `hostname` | str | host that began the run (Temporal: the control worker) |
| `started_at`, `finished_at` | str \| null | UTC ISO-8601 with `Z`; `finished_at` null until the verdict is written |
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
| `step`, `agent` | str | chain step (`investigate`, `probe.control.r1`, ...) and agent name |
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
| `outcome` | object | `label`, `rule_id`, `terminal_reason`, `finding`, `fix`, `fix_reason` (str \| null) and `probes`: {revision: {role: {`outcome`, `facts` (`ProbeFacts`), `duration_s`, `patch_sha256`, `image_digest`, `tree_sha256`, `cleanup_confirmed`}}} |
| `review` | object | `rounds` and per author (`control`, `exploit`): `first_review_valid`, `revisions_used`, `final_valid`, `recovered` |
| `models` | [str] | distinct model ids used |
| `agents` | {agent: object} | per agent, in first-call order: `calls`, `steps`, `models`, `prompt_versions`, `requests`, `input_tokens`, `output_tokens`, `tool_calls`, `retries`, `wall_s`, `statuses` ({status: count}) |
| `totals` | object | `agent_calls`, `requests`, `input_tokens`, `output_tokens`, `tokens`, `tool_calls`, `retries`, `agent_wall_s`, `wall_s` (run start to finish) |

## Other files

`case.json` (the Case), `verdict.json` (the Verdict; each `ProbeRun` carries `image_digest`, the image id its
container ran from, and `tree_sha256`, the environment's tree; Decide drops a run whose tree is not the case
revision it claims), `timings.json` (per-stage wall time), `stages/<step>.json`, `agents/<step>.messages.json`
(native message history) and `grounding.json`.
