# Corsair v2 benchmarks and evaluation reports

Corsair v2 uses **Pydantic Evals `Dataset`/`Case` objects directly**. There is no parallel YAML schema and no web console. A dataset task receives only `Case.inputs`; expected labels stay in `Case.expected_output` and evaluator metadata, never in an `AnalysisInput` or `RunSpec` passed to an agent.

## Dataset modes

| Mode | Native input | Task output | Claim boundary |
|---|---|---|---|
| `source` | `AnalysisInput` | `vulnerable`, `safe_in_scope`, or `unknown` | Source classification only; never an execution disposition. |
| `run` | `RunSpec` | a narrow `Verdict.status` string | Uses the ordinary engine and remains qualified only when its frozen evidence supports that verdict. |

`load_dataset(path, mode)` loads a standard native Pydantic Evals JSON/YAML serialization and restores `AnalysisInput` or `RunSpec` from its explicit `metadata.input_kind`. `save_dataset()` writes the standard native serialization. A mode mismatch is an error.

## Public importers

### OWASP Java/Python

`import_owasp(labels, source_root, language, revision, labels_sha256, suite_name, selected_ids=None, limit=None)` verifies the supplied label file's SHA-256 and parses only its pinned positional four columns. `true` becomes expected source prediction `vulnerable`; `false` becomes `safe_in_scope`. Each selected `BenchmarkTestNNNNN` must resolve to **exactly one** matching source-file stem; missing or duplicate matches abort the import, so no selected label disappears silently.

The importer requires a local checkout already pinned to the exact `revision`; it does not download or execute OWASP. It records raw path/digest and license provenance in metadata. It passes an agent a neutral digest-based filename after the documented `corsair-owasp-comment-and-test-header-strip-v1` source-only transform:

1. lexical `//`/`/*…*/` or Python comments are removed while preserving string literals;
2. recognizable Java JUnit and Python pytest/unittest decorator/test headers are removed; and
3. remaining source lines are unchanged.

The transformed source is intentionally not presented as executable source. This prevents ordinary label-revealing headers/comments from becoming an input feature. CWE, upstream truth, category, raw path, and digests remain sealed metadata; `AnalysisInput.cwe` is empty. OWASP is public synthetic development data, not a holdout and not an execution benchmark.

### Private OWASP development-smoke capture

The ignored local artifacts `.state/benchmarks/owasp-dev-sample.yaml` and `.state/benchmarks/owasp-dev-sample-pin.json` are a frozen eight-case **public-development smoke sample**: four Java and four Python source-only cases, each language balanced at two upstream `true` and two `false` labels. The pin manifest records the official repository URL, immutable HEAD/tree and parent IDs, CSV SHA-256, and every selected raw source-file byte hash.

Selection is mechanical rather than hand-picked: sort source-admissible labels by `BenchmarkTest` ID, select two `true` and two `false` cases per language, and prefer a previously unused CWE until no such row is available. The artifact is explicitly non-promotable and not comparable to an upstream score. It is **not an uncontaminated holdout** and must not support a general accuracy claim. Comment/header stripping and neutral filenames reduce ordinary leakage, but Java source and class names can still retain upstream test identities.

### PrimeVul

`import_primevul(jsonl, sha256, suite_name, ..., default_language="C/C++", license_ref=..., snapshot_provenance=...)` accepts a pinned local JSONL snapshot only. An actual upstream PrimeVul function row has `func`, `target`, `project`, and 40-hex `commit_id`; it has **no** language field. Canonical rows therefore use the caller-controlled `default_language` (default `C/C++`) and have no inferred or hard-coded CWE. Existing normalized local rows with `lang` and `commit` remain compatible.

The caller must retain a concrete `license_ref` and `snapshot_provenance` for the exact JSONL artifact. Corsair does not infer a data license from the PrimeVul repository license and does not assert that a snapshot is MIT-licensed. The legacy `license` and `label_provenance` keyword names remain compatibility aliases but have no defaults. `target=1`/`0` maps to `vulnerable`/`safe_in_scope`; it is classifier evidence, not an executable proof.

### Vul4J

`import_vul4j(..., selected_ids, repo_mapping=..., source_service=...)` accepts a standards-compliant quoted CSV and an explicit selected subset. To avoid untrusted raw dataset commands, it requires a local, already acquired mapping for each `repo_slug`:

```python
{
  "owner/project": {
    "path": "/absolute/already-acquired/repository",
    "baseline_commit": "<exact vulnerable parent SHA>",
    "candidate_commit": "<exact human-patch SHA>"
  }
}
```

The candidate must equal the immutable SHA at the end of `human_patch`. When a `SourceService` is supplied, it captures both pinned revisions through its trusted native Git path before a `RunSpec` is emitted. The importer does not run `compile_cmd`, `test_cmd`, `failing_tests`, or any dataset-provided shell string. A paired case expects `verified_repair`, but an actual engine run may correctly return `inconclusive`, `unqualified`, or another non-confirming terminal state when controls/evidence are missing.

## Bundled smoke dataset

`src/corsair/v2/data/corsair-smoke-v1.yaml` contains eight original Apache-2.0 source-only examples: balanced vulnerable/safe Python, Java, JavaScript, and C examples across CWE-22 and CWE-78. Its metadata always includes:

- `suite_kind: smoke`
- `generated: true`
- `promotion_eligible: false`
- `split: public-dev`
- `not_comparable_to_upstream: true`

Smoke scores are **wiring checks, not real-world accuracy**. Smoke results cannot be promoted as production baselines and cannot be compared with an upstream report.

## Evaluation and telemetry

`evaluate_dataset(dataset, config, output_dir, mode=..., repeat=..., max_concurrency=...)` delegates repeat, concurrency, task failures, and report generation to native `Dataset.evaluate`. It sets `logfire.configure(send_to_logfire=False)` before evaluation: traces remain local and no labels/source are exported to Logfire SaaS.

Production integration is deliberately narrow:

```python
# source mode
await corsair.v2.runtime.analyze_case(inputs, config)  # -> AnalysisResult

# full-system mode
await corsair.v2.engine.run(spec, config)              # -> RunResult
```

The evaluator projects those objects to their narrow output string, keeps stage roles/models/latencies/trajectory availability in local Evals attributes, and emits native numeric metrics only when usage is observable. `None` stays `null`/`unknown`; a zero is exported only when `StageMetrics.field_availability[field] == "reported_zero"`. Native `MaxToolCalls`, `MaxModelRequests`, and declared native `TrajectoryMatch` remain in the report. Missing local spans are reported as trajectory `unknown`, not a zero-tool pass. Do not enable `retry_task`: durable/effect retries belong to the engine and transport uncertainty remains separately unknown.

The source evaluator checks in-slice citations. The run evaluator checks evidence retention for decisive statuses. `EqualsExpected` is the correctness assertion. Returned blocked/abstaining terminal statuses remain cases; task exceptions remain native `report.failures` and are never counted as true negatives.

## Exports and comparison

`export_report(report, output_dir, metadata)` writes:

- `evaluation-report.json`: local native-report projection, records, complete summary, and immutable identity;
- `evaluation-records.csv`: one case or task-failure row per attempt;
- `evaluation-strata.csv`: language/framework/CWE/agent/model complete-denominator strata; and
- `evaluation-report.txt`: the native Pydantic Evals rendering.

Summaries expose all attempts, scored, correct/all, correct/scored, coverage, abstained, blocked, task/evaluator errors, false positives/negatives, nullable request/tool/token/cache/reasoning fields, duration median/p95, and repeated-trial instability. Execution status errors remain rows instead of being discarded.

`compare_reports(baseline, candidate, output_dir)` requires an identical immutable case/source/expected-label identity, split, task mode, evaluator policy, and execution profile. Agent/model/prompt/provider/config changes are recorded as experiment deltas rather than rejected. The paired CSV includes missing and error rows explicitly. `promote_baseline(report_path, root)` creates only a SHA-256-addressed reference after rejecting smoke reports and reports without explicit immutable identity.

## Telemetry field availability

`StageMetrics` now carries a typed immutable `field_availability` map with `reported`, `reported_zero`, `not_reported`, `not_applicable`, or `unknown` for each usage field. The evaluation adapter uses this typed provider-boundary fact first and reads the older `metrics.usage_details.field_availability` envelope only as a compatibility fallback. An unannotated numeric zero remains `unknown`; zero is exported only when the typed availability is `reported_zero`.

## Model trials and final validation boundary

The previously reported **Qwen 1.5B on CPU** run over eight OWASP cases was an exploratory public-development trial with zero usable predictions under the required typed-output/tool contract. A separate **GPT-5 mini** run reported five correct outcomes out of eight with 100% coverage; it is a pilot only (`n=8`, public-development data), not a production score, a held-out result, or a broad quality claim. These figures describe those preliminary attempts only and are not substituted for a fresh policy/model validation. A valid endpoint/schema alone is insufficient: before meaningful work, verify that the selected provider/model actually calls every required native tool and returns the required typed output. The parent-owned [validation record](validation.md) is the place for frozen-log results of current live tests; do not infer or add final counts here.
