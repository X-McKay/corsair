# Agent roles

Corsair has two bounded Google ADK roles. They propose or review structured data inside an investigation; they do not execute targets, decide a security finding, or operate the durable workflow. The surrounding trusted code admits source, runs the configured observer, validates immutable evidence, and applies the final policy. See the [architecture overview](../architecture/overview.md) for package ownership.

| Role | Objective | Agent-visible material | Native output | Tools |
| --- | --- | --- | --- | --- |
| Producer | Propose one declarative benign/adversarial payload pair for the admitted Python recipe. | Finding, public recipe configuration, bounded source excerpt, current round, and any prior submission/feedback. Execution outcomes, private fixtures, manifests, case paths, and verifier oracles are excluded. | [`Submission`](../../src/corsair/contracts/agents.py), including a nested `PlanRevision`. | `read_file`, `list_files` only. |
| Auditor | Decide whether a complete producer claim and payload pair are semantically coherent with the reported mechanism. | Finding, public recipe configuration, source excerpt, and submission. It receives no observation, execution outcome, private fixture, or expected label. | [`AuditResult`](../../src/corsair/contracts/agents.py). | None. |

The producer may choose data values for the configured payload parameter. It cannot change the callable, fixed arguments, fixture, exception policy, target source, or expected control behavior. It does not author assertions or executable probes. The auditor is outcome-blind: its decision is a semantic review, not a statement that code ran, a private value was observed, a fix succeeded, or a final disposition is justified.

## Native structured episodes

Each role factory declares the existing Pydantic contract directly through `LlmAgent.output_schema`: `Submission` for the producer and `AuditResult` for the auditor. The canonical models remain defined once under `corsair.contracts`; this guide is not a second schema definition.

The native ADK runner creates one fresh in-memory session and ordinary `Runner.run_async` episode per role activity. Temporal coordinates the bounded rounds, cancellation, final recording, and durable state through ordinary activities. Corsair does **not** use the upstream Google ADK Temporal plugin/integration.

Native before-model, after-model, and before-tool callbacks account for calls and usage and enforce the configured episode limits. Schema-plus-tools behavior is model-capability-dependent: where the SDK needs it, ADK may use its own schema-completion (`set_model_response`) handling. That path is budgeted and validated like any other tool call; it is not a universal live-model qualification claim. Corsair adds no custom `submit` tool, mutable completion flag, string-to-object decoder, or application repair layer. After native generation, Pydantic validation and exact round/parent-revision checks still apply.

## What agents cannot establish

A syntactically valid proposal or audit does not prove a vulnerability. Only the trusted verifier can run the operator-owned recipe, collect immutable artifacts, and validate an observation. Only the policy layer can derive a scoped disposition from admissible evidence. Frozen oracle labels remain in evaluators and never enter agent packets.

The implementation supports admitted **local** source snapshots only. It does not implement remote SCM checkout, Bedrock integration, a general HTTP API, or a generic provider/agent framework. The Python workflow API is not an HTTP service. The current pilot also makes no production, hostile-target-integrity, or population-accuracy claim.

For role-local capability details, see [tools and runtime instructions](tools-and-skills.md); for controlled changes, see [agent development](development.md); and for qualification interpretation, see [agent evaluations](evaluations.md). Current work and open limitations are indexed in the [plans](../plans/README.md).
