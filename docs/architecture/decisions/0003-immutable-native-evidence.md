# ADR 0003: Immutable native evidence

- **Date:** 2026-10-25
- **Status:** Accepted — implemented

## Context

A model proposal is not security evidence, and a container exit alone is not an attributable observation. Corsair must bind the native control/adversarial run to an admitted source snapshot, payload submission, reviewed image, recipe, and budget. It must also handle process interruption without blindly re-running a possible side effect.

The pilot uses local artifacts and Docker-native execution, so any evidence architecture must be honest about cleanup, host loss, and hostile-target limits.

## Decision

Corsair stores content-addressed immutable source snapshots, manifests, operation intents, raw role receipts, evidence bundles, observations, and final results. A manifest binds request/configuration, schema/prompt/capability/risk digests, model names, and image identity. Before execution, trusted code immutably claims an operation intent. After both role receipts are validated, it commits an observation mapping only when referenced artifacts are present.

The verifier accepts an observation only after checking operation/source/submission/image identity, raw receipt/driver structure, confirmed cleanup, host Docker and driver exit agreement, JUnit status, and relevant coverage. The sandbox returns an artifact reference, never a trusted verdict. If an operation intent exists but no matching committed observation can be reconciled, the result remains operationally uncertain and the execution is not replayed automatically.

## Alternatives considered

1. **Keep mutable in-memory observations or model-authored verdicts.** These lack durable identity binding and let an untrusted role influence a conclusion directly.
2. **Treat any container non-zero exit as proof.** A non-zero exit can be an execution failure; only the explicit validated evidence mapping is admissible.
3. **Automatically retry interrupted or unknown operations.** This can duplicate target execution and conceal uncertainty.
4. **Rely on Temporal history alone.** Temporal does not reconstruct an unrelated local artifact store or raw Docker receipt.
5. **Claim the container as universal hostile-code attestation.** Docker containment and receipt validation do not prove arbitrary interpreter, daemon, or kernel integrity.

## Consequences

Results are attributable to immutable identities and can be reconciled after a completed operation. Cleanup confirmation becomes an evidence condition rather than an implementation detail. Operators must preserve the artifact root alongside Temporal persistence; local artifact-host loss is unrecoverable without an external backup or shared durable store.

This design deliberately surfaces an interrupted/unknown operation as uncertainty instead of converting it into a positive or negative conclusion. It also preserves the distinction between a scoped component demonstration and broader application or patch claims. See [Data flow](../data-flow.md), [Deployment architecture](../deployment.md), and the authoritative [risk assessment](../../../src/corsair/policies/risk.md).
