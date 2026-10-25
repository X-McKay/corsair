---
id: ISSUE-0010
kind: issue
title: Live producer chooses an invalid follow-up probe on the safe case
status: open
updated: 2026-10-25
related: [PLAN-0110, PLAN-0111, ISSUE-0009]
---

# Live safe-case follow-up probe

The native ADK/Pydantic structured-output validation bug is resolved under ISSUE-0009. Its unchanged isolated producer freeze passes 3/3, and the auditor freeze passes 6/6. A separate actual model/worker/Docker/Temporal batch on the physical Mac scored **2/3** using the unchanged external oracles. Case01 completed `SUPPORTED` with valid original/fixed evidence; case03 completed `CONDITIONAL` with valid component evidence.

Case02's first round had both control and adversarial `PROPERTY_HELD`, with native target execution and cleanup confirmed. On a second bounded round the model returned another structurally valid string payload; its control still held, but adversarial native observation reported `execution_error`. The application correctly ended `ERROR` / `INCONCLUSIVE`, not a successful negative clearance. The external scorer retained one operational failure. No invalid positive evidence or forbidden labels were reported. Cleanup was confirmed for all completed native receipts.

This is a semantic candidate-selection/target-execution limitation, not a recurrence of stringified nested plans, an adapter placeholder, a target-policy denial, or evidence that the safe application is vulnerable. Do not loosen the exception policy, relabel the oracle, swallow the error, automatically replay an uncertain operation, or stop all iterative investigations after the first non-positive round just to make this small dataset green.

Private evidence: `.runs/structured-output-20261025/live-batch.json`, the committed result for `structured-live-batch-20261025.c1.r0`, and its per-round raw native artifacts. Lifecycle diagnostics remain under `.work/structured-output-20261025/` and are not publication material.

An appropriate next bounded agent change is an explicit, Pydantic-typed no-grounded-candidate outcome or better source-grounded follow-up selection, evaluated independently on positive, safe, retry and abstention cases before changing durable composition. The current model/schema is not claimed to achieve population-level accuracy, and full live-dataset qualification remains partial.
