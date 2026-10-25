# Data flow

An investigation turns an operator-admitted request into a bounded sequence of proposals, observations, reviews, and an immutable result. Models can propose typed payload data and review a proposal; they cannot directly turn a result into a security disposition.

```text
request + settings
      │
      ▼
prepare ──► manifest + immutable admitted source snapshot
      │
      ▼  (each bounded Temporal round)
producer ADK episode ──► Submission
      │                     │
      │                     ▼
      │              immutable operation intent
      │                     │
      │                     ▼
      │             Docker control/adversarial roles
      │                     │
      │                     ▼
      │             raw receipts → verified Observation
      │                                      │
      └──────────────────────────────────────┼──► outcome-blind auditor episode
                                             ▼
                              trusted policy decision / optional fixed-source check
                                             │
                                             ▼
                              immutable result artifact and committed mapping
```

## 1. Admission and run identity

The request identifies the recipe, finding, bounded budget, and source to be admitted. `prepare` first resolves the configured immutable Docker image identity, then admits the source through the local snapshot adapter. Admission uses descriptor/no-follow checks, rejects unsafe/sensitive entries, produces deterministic bounded archive bytes, and can enforce an expected digest. The resulting `PreparedCase` refers to an artifact rather than a live checkout path.

A `RunManifest` records the request/configuration identity, image ID, selected model names, prompt and agent-spec digests, output-schema digests, budget digest, and risk-assessment digest. These identities make a receipt attributable to the resources actually used; they do not make the source or target universally trustworthy.

## 2. Proposal episode

For each permitted round, the workflow creates a fresh producer activity with remaining model/tool budget, current revision context, and any admissible feedback. The ADK runner receives a bounded packet that excludes private fixtures, verifier oracles, execution observations, and case paths. The producer may use only `list_files` and `read_file` on the admitted snapshot, then returns the native `Submission` schema.

Native before-model, after-model, and before-tool callbacks account for attempts and enforce episode limits, including SDK schema-completion tools when applicable. After ADK returns, Corsair validates the canonical Pydantic model and the round/parent relationship. A no-output, invalid-output, budget, provider, or timeout condition remains typed feedback or an operational result; it is not repaired by a second application-owned parser.

## 3. Evidence execution and reconciliation

Before any target execution, trusted code writes an immutable operation intent containing the operation, source, submission, configuration, recipe, image, budget, and fixed-source identities. If a matching completed operation exists, its committed observation is read and revalidated. If an intent exists without a committed observation, the operation is uncertain and is not automatically replayed.

For a new operation, the Docker adapter materializes the immutable snapshot and public fixtures into read-only mounts, creates private fixture material at execution time, and runs one fresh container for each control and adversarial role. It returns raw artifacts, not a conclusion. Verification checks raw/driver identity, cleanup confirmation, source and submission digests, image identity, native exit/JUnit agreement, and relevant coverage. Only then is a validated `Observation` committed with the evidence bundle.

## 4. Review, decision, and fixed source

The auditor sees the source-grounded submission but no execution outcome. Its structured review is one input to trusted pure policy code; evidence and policy gates determine whether a scoped disposition is allowed. A demonstrated component result can remain `CONDITIONAL` for application exposure. A failed or blocked reproduction is `INCONCLUSIVE`, never a negative certificate.

When a supported or conditional result has a configured fixed source, the workflow runs a separately identified fixed-source evidence operation. That result means only that the submitted demonstration was blocked while the benign control remained valid; it does not certify a general fix.

## 5. Durable result

Temporal persists workflow coordination and executes activities with a single attempt for model and native side effects. The final `record` activity is separately idempotent and retryable, storing a result artifact and immutable operation mapping. Worker/client recovery therefore needs both Temporal history and the shared artifact root. A lost local artifact host cannot be rebuilt from Temporal history alone.

This is episode-level durability, not turn-level checkpointing inside a model call. [ADR 0001](decisions/0001-sdk-owned-durable-rounds.md) explains that tradeoff; [ADR 0003](decisions/0003-immutable-native-evidence.md) explains the evidence/reconciliation choice.
