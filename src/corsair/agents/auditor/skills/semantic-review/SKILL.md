---
name: semantic-review
description: Review a supplied Corsair producer packet for semantic coherence with a reported disclosure mechanism. Use when deciding whether a complete payload claim is supported, insufficiently grounded, or must be rejected without creating evidence.
---

# Semantic review

1. Read only the supplied packet. Decide source/ABI sufficiency before judging
   reachability or outcome. The admitted source excerpt, declared recipe and
   fixed arguments, submission, and public observer fixture location are the
   available context.
2. Return `INSUFFICIENT_CONTEXT` only when that packet leaves a link needed to
   judge the proposed test absent or ambiguous. Do not require an executed
   observation, private fixture contents, coverage, environment details, or
   broad application proof for an otherwise complete local mechanism.
3. On a sufficient packet, compare the stated hypothesis with the visible
   mechanism. Reject a materially false, unrelated, or concrete bypass claim
   contradicted by source. Do not repair it into a different claim.
4. Otherwise, accept a coherent proposal when its benign and adversarial
   payloads contrast at the caller-controlled property and invoke the real
   declared callable with its fixed arguments, rather than a substitute or a
   model-authored test.
5. Require a proposed disclosure observation to concern the specified private
   fixture, not attacker-controlled echoing, success, or an arbitrary marker.
   Do not require that observation to have happened. A proposal that honestly
   expects a visible guard to hold, block the input, or prevent disclosure may
   still be accepted as a guard test; reject it only if it instead claims the
   guard is bypassed despite the supplied source.
6. Do not create facts, execution evidence, coverage, private values, or
   negative clearance. Semantic acceptance is not a finding disposition.
