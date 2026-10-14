# Corsair v2 architecture

Corsair v2 is an operator-run **Python CLI/library**, not a website or web console. It is an isolated surface (`corsair-v2` / `corsair v2`); the legacy `corsair run` remains separate. See the [operator guide](README.md), [quickstart](quickstart.md), [OpenShell boundary](openshell.md), [benchmark guide](benchmarks.md), [metrics/export contract](metrics.md), and the parent-owned [live validation record](validation.md).

## Runtime path

```text
CLI / Python API
  -> validated Pydantic contracts + operator configuration
  -> shared engine coordinator
     -> PydanticAI agents and Harness capabilities
     -> native OpenShell adapter for untrusted workload lifecycle/effects
     -> immutable local evidence/store
  -> deterministic validity/disposition gates

Durable mode: one native Temporal parent workflow calls the same coordinator;
PydanticAI TemporalDurability emits fine-grained model/tool/workspace activities.
```

The direct engine and durable workflow share the run coordinator. Expected evaluation labels are held in native Evals `Case.expected_output`/metadata; they are not agent inputs. The agent's typed proposals are evidence inputs to deterministic gates, never the authority for a final conclusion. A missing, blocked, unqualified, invalid, skipped, or uncertain boundary stays an honest non-confirming state.

## Contract and CLI surface

`corsair-v2 schema operator|run|source-analysis --json` exports the current Pydantic JSON Schema. `RunSpec` is a typed request (`schema_version`, `request_id`, `source`, `concern`, optional `language`, `framework`, `cwe`, and repair fields), not a shell recipe. `AnalysisInput` is source-only and returns a narrow classification; it does not run a workload or issue an execution verdict. Inspect schema output and `corsair-v2 <command> --help` for the exact current fields and arguments; do not copy guessed command flags.

The operator config (`operator-v2`) carries `storage_root`, `default_model`, optional `role_models`, a `sandbox` profile, bounded `budget`, Temporal address/namespace/TLS/API-key environment-name/task-queue settings, and telemetry privacy settings. Model profiles select one of the admitted native routes: `ollama`, `openai`, `openai-compatible`, or `bedrock`. The `init` command currently defaults to `qwen3:4b` and `provider=ollama`; an explicit base URL is used for Ollama. A loopback local endpoint can use its provider-native path without storing a key; remote providers read only the named environment variable. The config contains an environment-variable **name**, never a secret. Provider/profile changes are experimental inputs, not quality evidence.

`init` creates a new mode-0600 config and refuses to replace an existing file. The sandbox image must be an OCI repository reference pinned by `@sha256:<64 lowercase hex>`; the policy must be an existing operator-owned file. The gateway setting is the **registered native OpenShell gateway name**, not a raw URL. Native registration/auth context is resolved by the OpenShell CLI/SDK in the configured user `HOME`. The optional `sandbox.cli_path` can select a local CLI binary in a manually reviewed config. Do not embed mTLS endpoint URLs or credential material in Corsair config.

CLI families include schema/config/doctor; direct or durable `run`; Temporal `worker`, `submit`, `status`, `cancel`, and history export/replay; UUID-bound `reconcile`; source-only `analyze`; dataset smoke/import and `eval`; compatible report `compare`; and digest-addressed baseline reference promotion. Their complete active interface is the installed CLI help. Outputs are operational JSON; private reports/evidence/history are written to operator-selected local paths.

## Native agents and Harness

The pinned application uses **PydanticAI 2.55.0** and **Pydantic AI Harness 0.55.0**. The factory loads operator-owned agent specifications using native `AgentSpec`/`Agent.from_spec` and supplies explicit Python capability instances. It does not accept repository-provided agent specs or dynamic model/capability authority.

Native `Agent` owns model requests, tool schemas/calls, structured Pydantic outputs, retries/validation, and `UsageLimits`. PydanticAI `Workspace` plus its `WorkspaceBackend` supports filesystem-facing tool capabilities. Harness contributes:

- `Skills` over fixed, operator-owned skill bundles and explicit role selection;
- `FileSystem` with a strict root, `read_only=True`, and bounded read/search/list tools for admitted captured-source access;
- `Planning` only where a role needs a plan, backed by native `SqlitePlanStore` with a run/stage session; and
- `ToolOutputLimits`, `ClearToolResults` (and other configured context limits) so oversized tool results are bounded and conversation context is controlled.

Native `UsageLimits` are derived from the operator episode/stage budget. Typed role output schemas and current-run validators constrain the model response; they do not establish semantic quality. There is no default Harness `Shell`, `Coder`, unrestricted writable workspace, model-created skill discovery, arbitrary subprocess, or agent-selected provider. The OpenShell workspace adapter is the narrow provider bridge that makes native workspace commands reach the same named workload; PydanticAI/Harness workspace APIs are not isolation boundaries.

## Temporal composition and lifecycle

Durable work is one `CorsairRunWorkflow` (`PydanticAIWorkflow`) using the native PydanticAI Temporal plugin. It invokes the shared coordinator, while native PydanticAI durability separately schedules fine-grained model, tool, and workspace activities. It does **not** wrap an opaque whole-agent trajectory inside one custom Temporal activity and does not create an agent workflow for each turn. Ordinary Corsair activities handle lifecycle/evidence boundaries; activity retry policies are effect-specific, and uncertain commands are not blindly replayed.

Task queues are `config.task_queue` plus the full `execution_identity(config)` suffix. That identity covers code/build, dependency/schema, configuration, policy and qualification inputs. Bind one immutable config/build identity to a worker/replay process; changes require a separate process and corresponding versioned execution identity/queue, not hot mutation of a live registration. Temporal workflow history/replay and a running real service remain separate validation questions. Temporal TLS and API-key authentication are explicit native client settings: `temporal_api_key_env` names an environment variable and is invalid unless `temporal_tls` is enabled.

The native Harness `SqlitePlanStore` is for task lists; it is distinct from the Corsair evidence store. No generic memory plane is configured.

## OpenShell workload boundary

`Sandbox` is the one v2 workload route. It uses the aligned `openshell==0.1.3` native CLI for create/upload/download and the pinned Python SDK for wait/get/exec/delete/reconciliation. It passes literal argv and never falls back to host, Docker, SSH, SCP, or an alternate runner. The adapter checks native UUID/labels/phase, stages captured bytes, executes bounded commands, and collects only declared bounded outputs. `prlimit` from util-linux is required for safe transfer file-size bounds; Python `preexec_fn` is not substituted.

The selected local Docker development profile is intentionally **unqualified**. A qualification file is an operator attestation bound by the application to SDK/CLI hashes, profile/image/base-policy identities, observed effective-policy digest, and runtime identifiers. It is not a signature from OpenShell, an independently issued cryptographic runtime proof, or an automatic certification mechanism. A missing gateway, policy/runtime gate, certificate, or identity is a blocker—not permission to run on the host.

OpenShell SDK delete is addressed by sandbox name and has no atomic expected-UUID conditional delete. The controller therefore requires exclusive ownership of its namespace/name domain plus UUID preflight and checks. A gateway acknowledgement/absence check is not independent evidence of driver garbage collection. Production qualification must be performed on the actual target host/profile; a development certificate must not be fabricated or supplied as a sample.

## Evidence and storage topology

V2 combines the local POSIX content-addressed immutable artifact store (reusing the `LocalArtifacts` primitive) with a SQLite WAL database for append-only run events, operation intents/idempotency, result receipts, and derived query state. `BEGIN IMMEDIATE` serializes commits across Store instances/processes on the same host; hashes and immutable references bind records to artifact bytes. This is a **single-host execution domain**, not a distributed database or storage service. It does not currently provide PostgreSQL, S3/object-store, shared multi-host CAS, or transparent multi-host access to host-local source/artifact paths. Increasing parallel work remains bounded to one execution domain; multi-host scaling needs a separately designed and qualified shared-storage/backend extension.

OpenShell upload/download and workloads are not transactional extensions of the evidence store. Staged source and returned files are treated as untrusted; a hash-matched transfer is an integrity receipt, not proof of execution or semantic validity. The exact evidence and refusal rules live in [OpenShell](openshell.md) and [metrics](metrics.md).

## Evaluation and qualification

Pydantic Evals `Dataset`/`Case`/`Dataset.evaluate` is the runner. `source` mode evaluates only `AnalysisInput`; `run` mode exercises the normal engine and returns the narrow terminal-status projection. The exporters retain task failures, abstentions and denominator distinctions; missing usage/trajectory data stays unknown rather than zero. The local smoke dataset is generated wiring data, not an upstream score, holdout, or promotable baseline. OWASP/PrimeVul source classification is not execution proof; paired Vul4J repair expectations are admitted only when the ordinary deterministic evidence gates pass.

Model output quality is not guaranteed by a valid JSON Schema or a successful health check. Before a model/profile is used for any meaningful workload, test that exact provider and model against the required typed output and native tool-use contract on the declared dataset/profile. Small local models can fail to call required tools or emit usable typed output; do not repair free prose into a prediction or treat zero usable predictions as success. Prior exploratory numbers, when included in a record, are explicitly non-final public-development observations. See [validation.md](validation.md) for the parent-owned actual live-test record; until then this document asserts no new live-test counts or final outcomes.
