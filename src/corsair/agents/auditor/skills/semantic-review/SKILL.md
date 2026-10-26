---
name: semantic-review
description: Review a supplied Corsair producer packet for semantic coherence with a reported security mechanism. Use when deciding whether a complete payload claim is supported, insufficiently grounded, or must be rejected without creating evidence.
---

# Semantic review

1. Read only the supplied packet. Check rubric rules R1, R2, R3 and R4 in order, citing the numbered source lines and recipe fields each one depends on. When the recipe `kind` is `python.command_sentinel/1`, load the `command-sentinel` reference for how R1, R2 and R4 read for that property.
2. `REJECT` when the packet contradicts any rule or the claim is incoherent; `rule` is the first contradicted id. Do not repair a false or unrelated hypothesis into a different claim.
3. `INSUFFICIENT_CONTEXT` when nothing is contradicted but the packet cannot establish a required link; `rule` is the first unestablished id.
4. `ACCEPT` only when R1 to R4 are all supported; `rule` is `ALL`.
5. Do not create facts, execution evidence, coverage, private values, or negative clearance. Semantic acceptance is not a finding disposition.
