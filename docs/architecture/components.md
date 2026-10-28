# Components and boundaries

Corsair keeps stable domain meaning separate from SDK-dependent execution. A bounded change should have one owning package, its consumers, and a visible qualification boundary.

| Component | Owns | Does not own |
| --- | --- | --- |
| `contracts/` | Canonical SDK-free Pydantic request, recipe, agent, evidence, result, and evaluation contracts | SDK objects or duplicate schemas |
| `agents/` | Producer/auditor metadata, prompts, canonical contract re-exports, factories, role-local tools, and packaged procedures | Workflow state, source admission, verdicts, or sandbox execution |
| `ports/` | Typed inference, source-snapshot, and sandbox contracts | Vendor SDK imports or a plugin registry |
| `adapters/` | Concrete ADK, local-source, Docker, filesystem, and Temporal integrations | Domain policy or durable-round decisions |
| `steps/` | Activity composition, manifests, evidence execution/reconciliation, and receipt validation | Temporal scheduling policy or model-authored judgment |
| `workflows/` | Deterministic Temporal coordination, deadlines, cancellation, and final recording | Filesystem, model, network, or Docker I/O |
| `policies/` | Disposition, fixed-source, and paired-assessment decisions | Evidence generation or operator authorization |
| `entrypoints/` | CLI, typed Python API, worker composition, diagnostics, and terminal output | An alternate scheduler |
| `observability/` | Sanitized lifecycle logging and native instrumentation | Prompts, source, payloads, credentials, or model reasoning |
| `evaluation/` | Frozen role diagnostics and external scoped scoring | In-band oracle access |

## Contracts and recipe observers

`contracts/sources.py` owns the discriminated recipe union. `JavaScriptRecipe` admits only a dependency-free named ESM export in a `.mjs` source file with an inserted JSON payload; its exception literals are exactly `Error`, `TypeError`, and `RangeError`. `JavaRecipe` admits only a public static `String` method with `String` arguments in a matching `.java` public class; its allowed exception names are qualified. No target dependency, target build script, or annotation processing path is part of either ABI.

`Settings.image_for_recipe()` selects the configured Python, Node, or Java tag. `DockerSandbox.image_id_for()` resolves the selected tag to an immutable local image ID for the manifest and receipt boundary.

The Node image contains the checked-in fixed `node:test` probe and projects native JUnit and LCOV output. The Java image contains the checked-in JDK observer with pinned JUnit Platform, JaCoCo, and Jackson dependencies; it compiles the one admitted target source with `javac -proc:none`, runs the fixed JUnit probe, and projects JaCoCo coverage. These concrete observers are separate from final qualification; actual native and composed results remain in [PLAN-0127](../plans/archive/plans/PLAN-0127-outcomes-node-java.md).

## Roles, ports, and evidence

`ProducerDecision` is the producer's native ADK output schema: a canonical `Submission`/`PlanRevision` proposal or explicit abstention. `AuditResult` is the outcome-blind auditor schema. Role-local contract modules re-export these exact canonical classes.

The producer reads only an admitted immutable snapshot through episode-private `read_file` and `list_files` tools. The auditor has private guidance only. Models propose data; the recipe observer emits a native receipt; `EvidenceVerifier` validates artifact, identity, report/exit agreement, coverage, and cleanup before policy evaluates a result.

A Temporal workflow coordinates deterministic state and named activities. The worker composes real adapters; activities own source preparation, producer/auditor episodes, evidence execution, and the final result record. Producer follow-up feedback is mechanical and contains no evidence label.

## Immutable results and scoring

Legacy disposition/execution status stays separate from result/2 `assessment_outcome`. Either completed outcome requires `COMPLETED` execution, accepted audit, valid receipt/coverage, cleanup, healthy control, and a valid actually executed adversarial role. `DEMONSTRATED` uses an adversarial disclosure. `NOT_DEMONSTRATED` is available only after the diverse finite protocol completes with held adversarial attempts; errors, audit rejection, repeated candidates, and uncertain operations remain unresolved.

The record activity commits one normalized immutable final result under `result.{run_id}`. Evaluation and CLI rescoring reconcile that reference and require the supplied result to match it; no separate scoring ledger is introduced. For negative assessment scoring, every retained expected operation must validate, not merely one held pair.

See [data flow](data-flow.md), [schemas](../reference/schemas.md), [testing](../development/testing.md), and [PLAN-0127](../plans/archive/plans/PLAN-0127-outcomes-node-java.md) for evidence status and current qualification gates.
