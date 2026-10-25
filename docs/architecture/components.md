# Components and boundaries

Corsair organizes stable domain meaning separately from SDK-dependent execution. The boundaries are intentionally small: a change should usually belong to one package, with its tests and qualification boundary visible from that package.

| Component | Owns | Does not own |
| --- | --- | --- |
| `contracts/` | Canonical SDK-free Pydantic contracts for requests, agents, source, evidence, results, and evaluation | SDK objects, provider-specific payloads, duplicate documentation schemas |
| `agents/` | Producer/auditor metadata, prompts, factories, and role-local tools | Workflow state, source admission, verdicts, sandbox execution |
| `ports/` | Narrow typed contracts for inference, source snapshots, and sandbox execution | Vendor SDK imports or generic plugin registries |
| `adapters/` | Concrete ADK, local-source, Docker, filesystem, and Temporal integrations | Domain policy or durable round decisions |
| `steps/` | Activity composition, manifests, evidence execution/reconciliation, and receipt validation | Temporal scheduling policy or model-authored judgment |
| `workflows/` | Deterministic Temporal round coordination, deadlines, cancellation, and result finalization | Nondeterministic I/O, model calls, or container creation |
| `policies/` | Pure scoped disposition/fix rules and the packaged risk assessment | Evidence generation or operator authorization |
| `entrypoints/` | CLI, typed Python API, worker composition, diagnostics, and terminal output | A separate web/API server or alternate scheduler |
| `observability/` | Sanitized lifecycle logging and native instrumentation | Raw prompts, source content, payloads, credentials, or model reasoning |
| `evaluation/` | Frozen isolated-role evaluation and external scoped scoring | Runtime fallback behavior or in-band oracle access |

## Domain contracts and agent roles

The contract modules are the sole schema authority. `Submission` with nested `PlanRevision` is the producer’s native ADK output schema; `AuditResult` is the auditor’s. They are validated after generation and are subject to dynamic round/parent checks and trusted evidence gates. A schema-valid object is neither a correct payload nor vulnerability proof.

The producer factory permits exactly two episode-private ADK tools: `read_file` and `list_files`. Both read a stored, hash-verified snapshot and are bounded by the request budget. The producer cannot submit executable code, pick a host path, modify source, change fixed arguments, inspect a prior execution, or acquire admission capability. The auditor has no tools and receives outcome-blind context.

## Ports and adapters

The three ports express concrete domain capabilities:

- `InferencePort` has typed `produce` and `audit` operations, rather than a generic role/payload call.
- `SourceSnapshotPort` prepares an admitted case and provides bounded immutable snapshot reads.
- `SandboxPort` exposes image identity, unknown-operation discovery, and one control/adversarial role execution that returns an `ArtifactRef`.

Ports import canonical contracts and standard-library types, never ADK, Docker, Temporal, or a concrete adapter. Activities require the ports explicitly; the ordinary worker constructs and supplies `AdkInference`, `LocalSourceSnapshots`, and `DockerSandbox`. This lets isolated evaluation and tests use controlled implementations without moving vendor objects into the domain.

The current SCM adapter is deliberately a local admission capability, not a generic Git client. Similarly, ADK’s model selection handles the currently implemented Gemini and LiteLLM-compatible paths; Corsair does not add empty OpenAI, Bedrock, GitHub, or Azure DevOps wrapper packages. Retired `runtime/`, `tools/`, `policy/`, top-level `cli.py`, and monolithic `contracts.py` paths are not compatibility APIs.

## Execution ownership

A Temporal workflow only coordinates deterministic state and calls named activities. The worker is the durable composition root; `Activities` receives its store and adapters and owns nondeterministic activity execution: source preparation, one producer episode, one auditor episode, native evidence execution, and final recording. `EvidenceVerifier` validates immutable artifacts before `policies/verdicts.py` derives an allowed scoped result. This separation prevents a model, an adapter, or a mutable provisional observation from directly asserting a release-facing conclusion.

See [Data flow](data-flow.md) for how these components interact, [Deployment architecture](deployment.md) for their runtime placement, and [ADR 0002](decisions/0002-pydantic-contracts-and-ports.md) for the implemented contract/port decision.


The steps package is the application/activity layer, not a second workflow engine. Shared file-relative source normalization is owned by the source adapter boundary and reused by request loading/evaluation; evaluators do not depend on CLI entrypoints. Agent factories accept native ADK model types directly rather than importing adapter-only aliases. Forbidden dependency directions are maintained test gates.
