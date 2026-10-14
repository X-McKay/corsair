# Corsair v2 operator CLI

Corsair v2 is a **local operator CLI/library**, not a website or web console. It uses an explicit operator-owned configuration to invoke native PydanticAI/Harness agents, native Temporal durability, OpenShell, and Pydantic Evals. Start with the [architecture](newarchitecture.md), [native-upstream decisions](newupstream-decisions.md), and [quickstart](quickstart.md). Parent-owned live results belong in [validation](validation.md); this guide asserts no new live result. Invoke it as either:

```shell
corsair-v2 --help
corsair v2 --help
```

The legacy `corsair run` command is retained unchanged. It is not a v2 alias and no v2 command silently falls back to a legacy runner, host execution, Docker execution, cloud inference, or telemetry export.

## Operating rules

- Run `corsair-v2 init` to create a **new** mode-`0600` configuration. It refuses replacement. `--image` must be an OCI `@sha256:` reference; `--policy` must already be a regular local operator policy; `--gateway` is a registered native gateway **name**, not a URL.
- `load_config` resolves policy, qualification, and storage paths relative to the config file, validates the policy, and rejects unknown schema fields. Model endpoint URLs cannot contain credentials. Put an API key only in the declared environment variable; never place it in a config, spec, or dataset.
- Run and evaluation exports are private directories (`0700`) with files (`0600`). `run` copies `result.json`, immutable `evidence.json`, and `report.md`; Temporal history export is also private because history can contain workflow payloads. Commands refuse to overwrite an existing output file.
- JSON is the stdout format. Output is intentionally operational: IDs, statuses, artifact paths/digests, and report counts, not prompts, captured source, credentials, or model rationale. Detailed evidence is in the private export/store.
- No command starts an external cloud inference request implicitly. `doctor` makes no provider call unless `--inference-health` is selected; then it sends only unauthenticated `GET /models` to a loopback endpoint or a URL supplied again with `--approved-base-url`.

## Commands

| Command | Native operation | Important behavior |
| --- | --- | --- |
| `init` | `OperatorConfig` + `write_config` | Creates a private config; defaults to `qwen3:4b` and native `provider=ollama` at the local Ollama API. No semantic/tool-use quality is implied. |
| `schema operator\|run\|source-analysis` | Pydantic model JSON Schema | Exports the actual `OperatorConfig`, `RunSpec`, or `AnalysisInput` schema. |
| `doctor --config` | package metadata, `Sandbox.health/profile_identity/qualified`, Temporal client connection | Reports observed SDK/CLI/gateway/profile/qualification and Temporal state. A prerequisite error is `ok:false` and exits nonzero; `qualified:false` is never relabelled healthy. |
| `run --config --spec [--durable] [--output-dir]` | `engine.run`, or `temporal.submit(..., wait=True)` | Runs direct or waits for the one native Temporal workflow, then exports its immutable retained artifacts. Cached direct request IDs receive the engine's immutable cached result. Unsupported, cancelled, and platform-failed terminal tasks return nonzero. |
| `worker --config` | `temporal.run_worker` | Polls the configured native Temporal task queue until signal-driven shutdown. |
| `submit --config --spec [--wait]` | `temporal.submit` | Starts the native workflow; `--wait` returns its actual `RunResult`. |
| `status` / `cancel` | `temporal.status` / `temporal.cancel` | `--graceful` sends the native safe-point stop signal; without it, native Temporal cancellation is requested. `--run-id` is the Temporal workflow ID. |
| `history export` / `history replay` | `temporal.export_history` / `temporal.replay` | Exports a fresh private history or replays it without business/model/tool effects. |
| `reconcile --config [--run-id]` | `Sandbox.reconcile` | Inspects known UUID-bound leases only; it never repeats an effect or declares an uncertain effect absent. |
| `analyze --config --input` | `runtime.analyze_case` | Runs the production source-only `AnalysisInput` role. It does **not** execute source or issue an execution verdict. |
| `benchmark smoke` | native `Dataset` serialization | Writes the bundled Apache-2.0 source-only smoke dataset. |
| `benchmark import-owasp` | `import_owasp` | Requires pinned local source, label SHA-256, exact revision, and optional explicit IDs. It never downloads or executes upstream content. |
| `benchmark import-primevul` | `import_primevul` | Requires an exact snapshot digest plus caller-provided `--license` and `--label-provenance`. |
| `benchmark import-vul4j` | `import_vul4j` | Requires an explicit selected subset and local JSON repository mapping; `--source-capture --config` captures pinned commits through `SourceService`, never dataset shell strings. |
| `eval` | `Dataset.evaluate` + `export_report` | Runs source or full-run native evaluation with explicit repeat and concurrency. |
| `compare` / `promote-baseline` | `compare_reports` / `promote_baseline` | Compares only identical immutable evaluation identities; promotion rejects smoke reports. |

Run `corsair-v2 <command> --help` for required arguments. The [quickstart](quickstart.md) shows safe shell variables and full config creation. `--gateway` accepts an OpenShell gateway registration name; native CLI/SDK registration and authentication use the configured `HOME` context, not a raw URL.

## Architecture, qualification, and report guidance

See [native architecture](newarchitecture.md), [accepted native-upstream decisions](newupstream-decisions.md), [OpenShell boundary/qualification limits](openshell.md), [benchmark use and claim boundaries](benchmarks.md), [metrics and exports](metrics.md), and the parent-owned [actual live validation record](validation.md). A policy/model can return schema-valid output while failing to use required tools or supply a usable typed result; test the exact provider/model on the declared benchmark before any meaningful workload.

## Library ownership map

| Responsibility | Owning implementation | What Corsair does not replace |
| --- | --- | --- |
| Config/schema | Pydantic contracts, `config.load_config`, `write_config` | No second config schema or credential store. |
| Agents, provider limits, native skills | PydanticAI + Pydantic AI Harness | No custom model loop, provider protocol, skill loader, or automatic cloud fallback. |
| Direct investigation | `engine.run` and its shared coordinator | No CLI-only investigation implementation. |
| Durable lifecycle/history | Temporal Python SDK + PydanticAI Temporal plugin | No home-grown scheduler or history format. |
| Workload lifecycle/commands/transfers | `Sandbox` with OpenShell v0.1.3 SDK/CLI | No host, Docker, SSH, or insecure gateway execution fallback. |
| Immutable evidence/source | v2 `Store` and `SourceService` | No mutable report substitution. |
| Datasets/evaluation | Pydantic Evals `Dataset`/`Case`/`Dataset.evaluate` | No separate benchmark schema or evaluation scheduler. |
| Report projections | `reports.export_report`, `compare_reports`, `promote_baseline` | No score-only report that discards task failures. |

## Evaluation reports and claim boundaries

Source mode takes `AnalysisInput` and returns only `vulnerable`, `safe_in_scope`, or `unknown`; it is classification evidence, not test execution. Run mode invokes the ordinary engine and projects its narrow `Verdict.status`. Expected labels remain in native `Case.expected_output`/metadata and are never passed as agent input.

Exports retain every attempted case and task failure, then provide language/framework/CWE/agent/model strata with: all attempts, scored and correct denominators, `correct_all`, `correct_scored`, coverage, abstentions, blocked cases, evaluator/task errors, true/false positive/negative counts, latency median/p95, repeat instability, request/tool counts, and input/output/cache/reasoning token fields. A missing metric is `null`/`unknown`, **not zero**. Local Logfire setup uses `send_to_logfire=False`; trajectories are local and a missing span is reported as `unknown`, not a no-tool pass.

Smoke data is only a wiring check: it is generated, source-only, public development data, not comparable with upstream suites, and cannot be promoted. OWASP and PrimeVul imports are source-only and do not prove execution accuracy. Vul4J paired cases require pinned local repositories but may still correctly finish as inconclusive, unqualified, unsupported, or failed when runtime/probe/evidence gates do not admit a repair claim.

`compare` requires the same frozen dataset/case/expected-label identity, split, task mode, evaluator policy, and execution profile. Model/provider/config changes are recorded as experiment deltas. A baseline promotion stores a SHA-256-addressed reference, not a copy of an unqualified claim.

## Qualification is separate from installation

A pinned package version, available Docker daemon, serialized YAML, or healthy-looking gateway does not establish an OpenShell qualification. The selected local Docker profile is intentionally unqualified. `Sandbox.qualified()` checks a configured non-symlink operator attestation against exact SDK/CLI/profile/image/base-policy, effective-policy, and runtime bindings; it is not a signed provider certificate or independent cryptographic proof. Actual target-host qualification remains required for production use.

Likewise, an installed Temporal SDK does not prove worker execution, a saved history does not prove successful replay, and an available model endpoint does not prove semantic accuracy. `doctor` reports what it actually observes; dependent commands surface native errors rather than fabricate health or a substitute run.

## Upstream references

- [OpenShell v0.1.3 release](https://github.com/NVIDIA/OpenShell/releases/tag/v0.1.3) and [OpenShell Kubernetes documentation](https://github.com/NVIDIA/OpenShell/tree/v0.1.3/docs/kubernetes)
- [PydanticAI Temporal durable execution](https://ai.pydantic.dev/durable_execution/temporal/) and [PydanticAI usage limits](https://ai.pydantic.dev/agent/#usage-limits)
- [Temporal Python SDK](https://docs.temporal.io/develop/python) and [replay](https://docs.temporal.io/develop/python/testing-suite#how-to-replay-a-workflow-execution)
- [Pydantic Evals datasets](https://ai.pydantic.dev/evals/datasets/) and [evaluation reports](https://ai.pydantic.dev/evals/reporting/)

These documents informed native API selection. They do not by themselves qualify any local profile, provider, workload, or security conclusion.
