# ADR 0005: Outcome-blind retry feedback carries no role-attributed run fact

- **Date:** 2026-10-25
- **Status:** Proposed — records the rule the implementation already follows; no behaviour change

## Context

[ADR 0004](0004-payload-pair-and-coverage-gated-verdict.md) makes the producer outcome-blind: it proposes a payload pair and never sees an outcome. Within one session the workflow retries the producer after a completed round that was not decisive, and `_retry_feedback` in [`workflows/investigation.py`](../../../src/corsair/workflows/investigation.py) decides what that retry may say. Today it forwards the auditor's rejection reason, or a fixed blind instruction when the auditor accepted.

A retry with a blind message is wasteful when the benign payload was simply wrong (the control did not hold, or the control run did not reach the declared line). It was proposed to feed back such control-role and structural facts, on the argument that they say nothing about the exploit role.

## The leak

The argument holds for one round in isolation but not for the retry channel. A retry is only issued after a completed, non-decisive round, so the producer already knows

> not (control healthy and covered, and exploit violated and covered, and audit accepted).

The audit term is already disclosed (a rejection is forwarded; its absence means acceptance). Any informative control-side message then partitions the remaining cause:

- a control defect is reported: the exploit outcome stays unknown;
- no control defect is reported: the control was healthy and covered, so **the exploit did not violate with coverage**.

The second branch tells the producer the exploit-role outcome by elimination, even though the feedback function never reads the adversarial role. Making the control branch indistinguishable from the healthy branch would remove the information the proposal wanted to add, so no informative control-role signal is outcome-blind on this channel. The same reasoning applies to any per-role coverage fact.

Operational facts do not need the channel: an operational `Observation.feedback` or a role `ERROR` already ends the session in the round loop, so no retry follows them.

## Decision

Retry feedback is a function of the audit output alone:

| Field that may reach the producer on retry | Why it carries no exploit-outcome information |
| --- | --- |
| `Feedback(gate="audit", reason=<auditor reason>)` when the audit rejected | The auditor formed it from hypothesis and payloads without any run result; given a rejection, the round's runs are irrelevant to the result. |
| `Feedback(gate="retry", reason=<fixed blind instruction>)` otherwise | A constant. |

No field of `Observation`, `RoleObservation` (control or adversarial), `decide()`'s reason or disposition, coverage, or fixed-revision evidence may reach `ProducerInput.feedback` after a completed round. `_retry_feedback` therefore takes only the `AuditOutput`, and a unit test pins that signature.

## Alternatives considered

1. **Control-role and structural feedback.** Rejected for the leak above.
2. **Always report control status, healthy or not.** Same information as (1).
3. **Treat integrity-invalid role evidence (stale identity, image mismatch, invalid JUnit) as operational and stop the session.** It would not use the producer channel and would save wasted rounds, but it changes the kernel's error path and so needs its own decision and the Docker and Temporal gates.
4. **Static pre-run checks of the benign payload against the recipe.** Outcome-free because nothing has run yet, but it belongs to submission admission in the producer adapter, not to retry feedback.

## Consequences

A producer whose benign payload is wrong still retries blind; rounds stay more expensive than they would be with the leak. Any future proposal to enrich retry feedback must show that the message carries no information about the adversarial role given the retry event, not only that its function never reads that role.
