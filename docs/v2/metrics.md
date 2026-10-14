# Evaluation metrics and exports

`corsair-v2 eval` runs the native Pydantic Evals dataset and writes a **new private output directory**. It is an operator report, not a web UI. The directory is mode `0700`; every export is mode `0600`; existing targets are never overwritten.

| Export | Contents |
| --- | --- |
| `evaluation-report.json` | Native report projection, immutable dataset identity, complete records, overall summary, all-dimension strata, and `by_dimension` rollups. |
| `evaluation-records.csv` | One row for every returned case and task failure. Formula-like CSV cells are prefixed safely. |
| `evaluation-strata.csv` | The full language/framework/CWE/agent/model cross-product strata. |
| `evaluation-report.txt` | The native Pydantic Evals render, including its evaluator reasons and failures. |
| `evaluation-summary.md` | Concise operator overview and language-only aggregate table. It is a projection; it does not run or replace the native evaluator. |

The JSON `summary` and each `by_dimension.<dimension>` object use the same report calculation. `by_dimension` includes `language`, `framework`, `cwe`, `agent`, and `model`; each contains a `summary` plus that dimension's `strata` rows. The complete cross-product remains in `evaluation-strata.csv`.

## Denominators and claims

- **All attempts** includes returned cases and task failures.
- **Decisive coverage** is scored attempts divided by all attempts. Abstentions and blocked outcomes are not scored.
- **Usable accuracy** (`correct_scored`) is correct scored outcomes divided by scored attempts. **All-attempt accuracy** (`correct_all`) uses all attempts as its denominator.
- Task failures have no fabricated terminal status, truth result, or token counts. Evaluator failures are counted independently.
- Precision, recall, F1, FP, and FN are meaningful only for usable, grounded two-class source classifications. A source-only `vulnerable`/`safe_in_scope` classification is **not** an executed security verdict.
- Request, tool, cache, reasoning, input-token, and output-token totals are present only when all relevant attempts reported the field. `<field>_known_sum`, `<field>_known_attempts`, and `<field>_unknown_attempts` preserve partial coverage. Unknown usage is not zero; a failed request can have billing that was not reported.

The summary Markdown table escapes language names containing pipes or newlines, reports median/P95 task duration, and makes partial token coverage explicit rather than inventing a total.

## Identity, comparison, and promotion

The evaluator provides the authoritative `evaluator_policy`, `config_digest`, `config_identity`, `build_identity`, and `native_profile_hashes`. Caller metadata that conflicts with a native value is rejected. Repeated trials are deduplicated by `source_case_name` for immutable dataset identity and must preserve source digest, expected truth, split/suite, and task mode.

`corsair-v2 compare` requires matching immutable dataset/case identity, split, task mode, evaluator policy, and execution profile. It keeps missing trial rows visible and reports intentional experiment deltas, including model/prompt/provider plus config digest/identity, build identity, and native profile hashes. These private outputs can contain detailed operator provenance and require user review.

`corsair-v2 promote-baseline` creates a SHA-256-addressed **evaluation baseline reference** only. It rejects smoke, generated, and explicitly promotion-ineligible records, including task-failure-only reports. A reference does not approve a model, establish evaluation quality, qualify a host/runtime, or make a production-security claim.
