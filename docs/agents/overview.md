# Agent roles

Corsair has two bounded Google ADK roles. They propose or review structured data inside an investigation; they do not execute targets, decide a security finding, or operate the durable workflow. The surrounding trusted code admits source, runs the configured observer, validates immutable evidence, and applies the final policy. See the [architecture overview](../architecture/overview.md) for package ownership.

| Role | Objective | Agent-visible material | Native output | Capabilities |
| --- | --- | --- | --- | --- |
| Producer | Return a grounded payload proposal or explicitly abstain when source grounding is unavailable. | Finding, public recipe configuration, bounded source excerpt, current round, prior submission/feedback when supplied, and its preloaded packaged procedure. Execution outcomes, private fixtures, manifests, case paths, and verifier oracles are excluded. | [`ProducerDecision`](../../src/corsair/contracts/agents.py): `proposal` wraps a `Submission` with `PlanRevision`; `no_grounded_candidate` carries a bounded reason. | Episode-private `read_file` and `list_files` only; no skill-loading tool. |
| Auditor | Decide whether a complete producer claim and payload pair are semantically coherent with the reported mechanism. | Supplied outcome-blind packet, including any bounded source context, and its preloaded packaged procedure. It receives no observation, execution outcome, private fixture, or expected label. | [`AuditResult`](../../src/corsair/contracts/agents.py). | None: no source, external or skill-loading tool. One JSON-mode request per review. |

The producer may choose data values for the configured payload parameter. It cannot change the callable, fixed arguments, fixture, exception policy, target source, or expected control behavior. It does not author assertions or executable probes. The auditor is outcome-blind: its decision is a semantic review, not a statement that code ran, a private value was observed, a fix succeeded, or a final disposition is justified.

## Native structured episodes

Each role factory declares the existing Pydantic contract directly through `LlmAgent.output_schema`: `ProducerDecision` for the producer and `AuditResult` for the auditor. The producer decision's `proposal` retains the existing `Submission`; `no_grounded_candidate` is an explicit `INCONCLUSIVE` abstention that schedules no target or audit work. The canonical models remain defined once under `corsair.contracts`; role-local contract modules re-export those same objects rather than defining alternatives.

The native ADK runner creates one fresh in-memory session and ordinary `Runner.run_async` episode per role activity. Temporal coordinates the bounded rounds, cancellation, final recording, and durable state through ordinary activities. Corsair does **not** use the upstream Google ADK Temporal plugin/integration.

Native before-model, after-model, and before-tool callbacks account for calls and usage and enforce the configured episode limits. Schema-plus-tools behavior is model-capability-dependent: where the SDK needs it, ADK may use its own schema-completion (`set_model_response`) handling. That path is budgeted and validated like any other tool call; it is not a universal live-model qualification claim. Corsair adds no custom `submit` tool, mutable completion flag, string-to-object decoder, or application repair layer. After native generation, Pydantic validation and exact round/parent-revision checks still apply.

## Packaged procedural guidance

Each role has one private packaged procedure: producer `source-grounding` and auditor `semantic-review`. Both are parsed by native ADK and preloaded into the role instruction; neither role has a skill loader, and no `SkillToolset` is composed. Preloading puts guidance into the agent context; it never executes a skill script, creates an environment, discovers a directory, grants a capability, or changes the packet.

The always-on role system instruction remains a separate package resource. It establishes the role's safety and output boundary; the preloaded procedure helps apply that boundary to the current packet. All admitted skill content participates in configuration and immutable operation identity. Preloaded procedure names are bounded accounting metadata, while unavailable usage or cost remains unknown.

## What agents cannot establish

A syntactically valid proposal or audit does not prove a vulnerability. Only the trusted verifier can run the operator-owned recipe, collect immutable artifacts, and validate an observation. Only the policy layer can derive a scoped disposition from admissible evidence. Frozen oracle labels remain in evaluators and never enter agent packets.

The implementation supports admitted **local** source snapshots only. It does not implement remote SCM checkout, Bedrock integration, a general HTTP API, or a generic provider/agent framework. The Python workflow API is not an HTTP service. The current pilot also makes no production, hostile-target-integrity, or population-accuracy claim.

For role-local capability details, see [tools and runtime instructions](tools-and-skills.md); for controlled changes, see [agent development](development.md); and for qualification interpretation, see [agent evaluations](evaluations.md). Current work and open limitations are indexed in the [plans](../plans/README.md).
