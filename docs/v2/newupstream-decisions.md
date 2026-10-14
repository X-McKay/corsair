# Corsair v2 native-upstream decisions

This record states the architecture decisions selected for the pinned Corsair v2 implementation. It is based on the repository's implementation research and native code paths; upstream documentation establishes API facts, not Corsair runtime qualification. See the [architecture overview](newarchitecture.md) and [live validation record](validation.md).

## ADR-1 — PydanticAI owns agent execution; Harness is selective

**Decision.** Use native `pydantic_ai.Agent`, `FunctionToolset`, `RunContext`, Pydantic structured outputs, provider/model classes, and `UsageLimits`. Build from trusted static `AgentSpec` objects using `AgentSpec.from_file(...)` / `Agent.from_spec(...)`; supply explicit Python capability objects. Use Harness `Skills` for fixed operator-owned digested bundles, `FileSystem` only as bounded read-only access to an admitted workspace, `Planning` when a role needs a plan, and native result/context limits such as `ToolOutputLimits` and `ClearToolResults`. The SQL plan store is `SqlitePlanStore`, scoped to run and role.

**Rationale.** These are the upstream agent, output-validation, workspace, skills, planning, and usage mechanisms; recreating loops, schema dispatch, skill loading, task lists, or token counters would duplicate them. The actual source access/execution boundaries remain explicit typed tools and the OpenShell adapter; Harness does not grant isolation or authority.

**Rejected.** Custom model/tool loop or provider protocol; repository-controlled manifests/capabilities; default `Shell` or `Coder`; unrestricted writable `FileSystem`; dynamic skill/subagent discovery; in-memory cross-worker plan state; interpreting schema validity as semantic accuracy.

**Pinned evidence/reference:** [PydanticAI documentation](https://ai.pydantic.dev/), [Harness documentation](https://ai.pydantic.dev/harness/). The selected tuple is `pydantic-ai-slim[openai,bedrock,temporal]==2.55.0`, `pydantic-ai-harness[skills]==0.55.0`, `pydantic-evals[logfire]==2.55.0`.

## ADR-2 — One Temporal parent, native fine-grained PydanticAI activities

**Decision.** One `CorsairRunWorkflow` (registered as `PydanticAIWorkflow`) owns the durable business lifecycle. The workflow calls the normal PydanticAI agents with `TemporalDurability` and the `PydanticAIPlugin`; PydanticAI supplies individual native model/tool/workspace activities. Only trusted lifecycle/evidence operations are ordinary Corsair activities. No whole-agent opaque activity and no child workflow per agent turn.

**Rationale.** This keeps deterministic orchestration and resumable request/tool work at native activity granularity without a second scheduler/graph. Stable workflow, agent, toolset/activity IDs and serialized reference-only context are replay compatibility data.

**Operations.** `temporalio==1.34.0`. Queue is the configured base queue plus the full `execution_identity(config)`; one immutable config/build identity belongs to one worker/replay process. Use separate versioned execution identities/queues and processes when those inputs change. Temporal API-key authentication is read through `temporal_api_key_env` and requires `temporal_tls=true`; no key value is stored in config. Retry policy is effect-specific; an interrupted side effect remains uncertain, not automatically replayed.

**References:** [PydanticAI Temporal durability](https://ai.pydantic.dev/durable_execution/temporal/), [Temporal Python](https://docs.temporal.io/develop/python), [Temporal replay](https://docs.temporal.io/develop/python/testing-suite#how-to-replay-a-workflow-execution).

## ADR-3 — OpenShell SDK/CLI, one unqualified Docker development profile

**Decision.** Keep the exact aligned OpenShell `0.1.3` SDK/CLI tuple. `SandboxClient` owns lifecycle/inspection/exec; the official CLI owns native upload/download with literal argv. A small Corsair adapter provides UUID-bound lease/state checking, bounded staging/collection, receipt storage, and uncertainty mapping. The workload runs only inside OpenShell; there is no host, Docker, SSH, or other fallback. Require `prlimit` (util-linux) to bound native transfers instead of unsafe Python pre-exec techniques.

**Rationale.** OpenShell exposes the required native sandbox boundary, but not Corsair's durable operation receipts, atomic file caps, or expected-UUID deletion API. The adapter implements only these application obligations. Exclusive controller ownership of the namespace/name domain is required because delete is name-addressed and not atomic against UUID replacement.

**Qualification.** The local Docker driver/profile remains intentionally **unqualified** until the exact target host, gateway, effective policy, runtime and workload have passed explicit qualification. A qualification file is operator attestation that binds exact SDK/CLI/profile/image/base-policy/effective-policy/runtime fields; Corsair's parser does not establish a provider-signed or independently cryptographically issued runtime proof. Do not fabricate an all-true certificate or use sample digests. Gateway deletion acknowledgement is not independent driver-GC evidence.

**References:** [OpenShell v0.1.3 release](https://github.com/NVIDIA/OpenShell/releases/tag/v0.1.3), [Python SDK](https://docs.nvidia.com/openshell/v0.1.3/sdk/python.html), [sandbox lifecycle](https://docs.nvidia.com/openshell/v0.1.3/how-it-works/sandboxes/overview.html), [qualification boundary](openshell.md).

## ADR-4 — Local immutable CAS plus SQLite WAL; no implied shared cloud store

**Decision.** Reuse local POSIX `LocalArtifacts` for content-addressed bytes and use SQLite WAL (`records.sqlite3`) for append-only run events, operation intents, idempotency receipts and result projections. Commits use SQLite write transactions (`BEGIN IMMEDIATE`) and are process-safe on the same storage volume/execution domain.

**Rationale.** This is a small native fit for one local operator domain and gives artifact hashes, transaction boundaries and durable receipts without another database service.

**Not implemented / rejected.** PostgreSQL, S3/object-store backend, shared multi-host CAS/database, host-local source paths on arbitrary workers, and transparent horizontal activity scaling across machines. Multi-host use requires a separately scoped shared storage backend plus transfer/path identity design and qualification; it is not currently an adapter plug-in or a ready stub. Concurrency is bounded within the single-host execution domain and may be isolated further by Temporal execution identities/queues.

## ADR-5 — Pydantic Evals is the evaluation runner

**Decision.** Use native `Dataset`, `Case`, and `Dataset.evaluate` with source-only and ordinary-engine run tasks, retained failures/abstentions, sealed `expected_output`, deterministic evaluators, local-only traces, and a thin JSON/CSV projection. Smoke is generated wiring data; OWASP and PrimeVul are source classification; paired Vul4J is scored only through the normal run/evidence gates.

**Rationale.** Native Evals supplies case execution/repeats/concurrency and report/evaluator interfaces. The Corsair projection adds complete denominators, immutable identity/comparison and unknown-not-zero usage semantics without a second eval loop or web console.

**Model gate.** A schema-valid response or successful model endpoint does not establish usable model behavior. Test each exact provider/model against required tools and typed output on the declared dataset before meaningful workload. Small local models may produce no usable typed predictions; do not parse prose as a substitute. Prior pilot figures, if noted, are public-development observations only—not production, held-out, or final results.

**References:** [Pydantic Evals datasets](https://ai.pydantic.dev/evals/datasets/), [reporting](https://ai.pydantic.dev/evals/reporting/), [benchmark boundary](benchmarks.md), [metrics](metrics.md).

## Final qualification boundary

These ADRs select native APIs and describe implementation. They do not assert that any OpenShell local profile is qualified, that a Temporal server/history/replay passed live, or that a provider/model meets the semantic/tool contract. Consult the parent-owned [validation record](validation.md) for actual run evidence once populated; absent that record, do not state new counts or conclusions.
