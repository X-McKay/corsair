# Components and boundaries

Corsair organizes stable domain meaning separately from SDK-dependent execution. The boundaries are intentionally small: a change should usually belong to one package, with its tests and qualification boundary visible from that package.

| Component | Owns | Does not own |
| --- | --- | --- |
| `contracts/` | Canonical SDK-free Pydantic contracts for requests, the payload pair, audit results, source, coverage/evidence, labels, and evaluation | SDK objects, provider-specific payloads, duplicate documentation schemas |
| `agents/` | Producer/auditor metadata, instructions, canonical-contract re-exports, factories, role-local toolsets, and packaged skills | Workflow state, source admission, probe authoring, verdicts, sandbox execution |
| `ports/` | Narrow typed contracts for inference, source snapshots, and sandbox execution | Vendor SDK imports or generic plugin registries |
| `adapters/` | Concrete ADK, local-source, Docker, filesystem, and Temporal integrations | Domain policy, kernel gates, or durable round decisions |
| `steps/` | Activity composition, manifests, probe materialization from the recipe and payload pair, differential execution/reconciliation, receipt and coverage validation | Temporal scheduling policy or model-authored judgment |
| `workflows/` | Deterministic Temporal coordination of episodes, gate order, session count, deadlines, cancellation, and result finalization | Nondeterministic I/O, model calls, or container creation |
| `policies/` | The pure kernel: gate decisions, the verdict table, `negative_threshold`, and the packaged risk assessment | Evidence generation or operator authorization |
| `entrypoints/` | CLI, typed Python API, worker composition, diagnostics, and terminal output ([presentation](#terminal-presentation)) | A separate web/API server or alternate scheduler |
| `observability/` | Sanitized lifecycle logging and native instrumentation | Raw prompts, source content, payloads, credentials, or model reasoning |
| `evaluation/` | Frozen isolated-role evaluation and external scoped scoring against labelled corpora | Runtime fallback behavior or in-band oracle access |

## Domain contracts and agent roles

The contract modules are the sole schema authority. `ProducerDecision` is the producer's native ADK output schema: a proposal carries a canonical `Submission` holding the benign/exploit **payload pair** and its `PlanRevision`, or the producer explicitly abstains. `AuditResult` is the auditor's: a structured review whose only effective decision is rejection. Both are validated after generation and are subject to round/parent checks and the kernel gates. Role-local contract modules re-export the exact canonical objects; they do not define a second schema. A schema-valid pair is neither a correct payload nor vulnerability proof.

The producer role toolset is exactly two episode-private ADK source tools, `read_file` and `list_files`; its procedure is preloaded into the instruction, with no skill loader. Both source tools read a stored, hash-verified snapshot and are bounded by the request budget. The producer cannot submit executable code or a probe module, pick a host path, modify source, change fixed arguments, inspect any execution, or acquire admission capability. It proposes payload data only; the kernel owns the recipe and writes the probe at run time ([ADR 0004](decisions/0004-payload-pair-and-coverage-gated-verdict.md)).

The auditor has **no tools**: `agent.json` declares none, `AgentSpec` rejects any, and its factory preloads `semantic-review` into the instruction, so a review is one JSON-mode request. It receives an outcome-blind packet (finding, public recipe configuration, source excerpt, proposed pair) and returns structured output. It never receives execution receipts, coverage, fixtures, oracles, or a prior label, and it cannot promote a label; a non-rejection merely lets the kernel continue past `blind_audit`.

No role composes a native ADK `SkillToolset` or exposes `load_skill`/`load_skill_resource`. Each factory parses its role's admitted built-package procedure with the native ADK skill parser and preloads it into the instruction; this does not execute a skill, create a capability, inject state, or provide a generic plugin registry. Admitted skill bytes are part of configuration and immutable operation identity.

## Ports and adapters

The three ports express concrete domain capabilities:

- `InferencePort` has typed `produce` and `audit` operations, rather than a generic role/payload call.
- `SourceSnapshotPort` prepares an admitted case and provides bounded immutable snapshot reads.
- `SandboxPort` exposes image identity and one differential run (control role and exploit role, same recipe and fixed arguments, different payload) that returns an `ArtifactRef` carrying raw receipts and per-run coverage.

Ports import canonical contracts and standard-library types, never ADK, Docker, Temporal, or a concrete adapter. Activities require the ports explicitly; the ordinary worker constructs and supplies `AdkInference`, `LocalSourceSnapshots`, and `DockerSandbox`. Isolated evaluation and tests use controlled implementations without moving vendor objects into the domain.

The Docker adapter is the pilot's only sandbox implementation. The port is kept so that an OpenShell adapter can be added later as a real, separately qualified capability; it is deferred, not stubbed. The SCM adapter is deliberately a local admission capability, not a generic Git client. ADK's model selection handles the implemented Gemini and LiteLLM-compatible paths; Corsair does not add empty vendor wrapper packages.

## Execution ownership

A Temporal workflow only coordinates deterministic state and calls named activities. The worker is the durable composition root; `Activities` receives its store and adapters and owns nondeterministic activity execution: source preparation, one producer episode per activity, one auditor episode per activity, one differential run per activity, and final recording. `EvidenceVerifier` validates immutable receipts and exact target-line coverage before [`policies/verdicts.py`](../../src/corsair/policies/verdicts.py) applies the gate order and verdict table. The workflow counts independent producer sessions toward `negative_threshold` and schedules the fixed-revision differential when a demonstration is observed. The admitted `negative_threshold` and `max_sessions` (default 2 and 2) come from worker settings once, at prepare, into the readable `RunManifest` fields of those names; the workflow schedules and aggregates from that replayed manifest, never from worker settings, and prepare blocks a case whose `max_rounds` times `max_sessions` exceeds the terminal result's round capacity. A further session starts only after every earlier one ended in a clean negative, while the remaining sessions could still reach the threshold and the root budget still admits a round. It is blind: its rounds restart with no previous submission or feedback, its evidence runs under `<run>.s<n>.r<i>` operation ids, and it shares the root LLM, tool and elapsed budgets (`independent-sessions-v1` patch gate, so earlier single-session histories still replay).

This separation prevents a model, an adapter, or a provisional observation from asserting a label. See [Data flow](data-flow.md) for how these components interact, [Deployment architecture](deployment.md) for their runtime placement, and [ADR 0002](decisions/0002-pydantic-contracts-and-ports.md) for the contract/port decision.

The steps package is the application/activity layer, not a second workflow engine. Shared file-relative source normalization is owned by the source adapter boundary and reused by request loading/evaluation. Agent factories accept native ADK model types directly rather than importing adapter-only aliases. Forbidden dependency directions are maintained test gates.

## Terminal presentation

[`entrypoints/terminal.py`](../../src/corsair/entrypoints/terminal.py) holds the `Terminal` class and its options protocol: it chooses JSON, Markdown or human output, waits on SDK completion with an optional status query, logs a failed command, and dispatches each human view to one module of [`entrypoints/render/`](../../src/corsair/entrypoints/render/). JSON and Markdown output never pass through `render/`.

| Module | Renders | Commands |
| --- | --- | --- |
| `common` | Shared cells, labels, digest abbreviation, signed deltas and clock durations | none on its own |
| `result` | Investigation result, verdict explanation and native reference observation | `investigate`, `inspect`, `explain`, `verify` |
| `reports` | Evaluation summary, scored rows, family/split tables, gate counts and report comparison | `eval`, `rescore`, `report`, `compare`, `dataset replay-candidates` |
| `runs` | Committed-run listing and per-role evidence receipts | `runs`, `inspect --evidence` |
| `checks` | Environment checks, dataset validation and scanner-intake dry run | `doctor`, `dataset validate`, `intake` |
| `preview` | Agent request preview and preview diff | `agent preview` |
| `progress` | Live progress panel and plain progress lines while a workflow runs | every command that waits on a workflow status query |
| `remedies` | The fixed next step logged beside a failed command | every command's error path; `doctor` checks |
