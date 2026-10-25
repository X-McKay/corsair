# Scorecard queries

Reference DuckDB SQL over **run records**: one newline-delimited JSON file per run
(`<run>.jsonl`), one object per investigated case. `read_json(..., filename = true)`
adds the originating file name as the `filename` column, so a directory of runs can be
cut by run. `corsair.evaluation.scorecards` executes these files with named parameters
(`$runs`, `$safe_label`, `$baseline`, `$candidate`) and returns typed rows; nothing here
calls a model, and the verdict in every row was decided by code upstream.

The queries declare the columns they read, so extra keys in a record are ignored and
missing keys read as `NULL`. No case, CVE, repository or runtime identifier is hardcoded;
`$safe_label` names the label whose false use is the costliest error
(`EXPLOIT_NOT_DEMONSTRATED` by default). All other labels are taken from the data.

## Expected row shape

| key | type | meaning |
| --- | --- | --- |
| `run_id` | string | identity of the run (shared by every row of one file) |
| `case_id` | string | identity of the investigated case |
| `input_digest` | string | sha256 of the frozen case input; `compare.sql` refuses rows whose digests differ |
| `language` | string or null | language stratum, from the case data |
| `runtime` | string or null | runtime/toolchain row used for the probes |
| `cwe` | string or null | weakness class of the finding |
| `label` | string or null | the verdict decided by code (`EXPLOIT_DEMONSTRATED`, `EXPLOIT_NOT_DEMONSTRATED`, `INCONCLUSIVE`, `UNABLE_TO_RUN`, `ERROR`); `null` when no verdict was recorded |
| `expected_label` | string or null | evaluator-joined oracle label; never present in agent inputs |
| `decisive` | boolean | whether the verdict counts as decisive for cost accounting (decided by code upstream) |
| `last_gate` | string or null | the last gate the run reached (for example `plan`, `build`, `check`, `review`, `verdict`) |
| `rejections` | list of `{gate, rule}` | every gate rejection with the audit rule that rejected it; empty when none |
| `llm_calls`, `tool_calls` | integer or null | usage; `null` means unknown, never zero |
| `seconds` | number or null | wall-clock agent seconds; `null` means unknown |

## Queries

- `scorecard.sql`: long format `(metric, label, numerator, denominator, value)` with per-label
  `precision`/`recall`, `safe_precision` and `false_safe_rate` for `$safe_label`, `decisive_rate`,
  `llm_calls_per_decisive`, `tool_calls_per_decisive`, `seconds_per_decisive` (over decisive rows
  whose usage is known) and `usage_unknown_rate`. `value` is `NULL` when the denominator is 0.
- `strata.sql`: the same counts cut by `language`, `runtime`, `cwe` and `last_gate`.
- `ledger.sql`: rejections grouped by `gate` and `rule`, with the number of distinct runs affected.
- `compare.sql`: a full outer join of a baseline and a candidate run on `case_id`; `comparable`
  is false when a case is missing on one side or its `input_digest` differs. The reader refuses
  the comparison when any row is not comparable, so metric deltas are only reported for runs over
  identical frozen inputs.
