# Design: a verdict kernel with one producer and one blind auditor

## Why

The previous architectures (v1 on `main`, v2 on `develop`) enforced rigour through role separation: an investigator,
a builder, two probers and a reviewer, each with typed contracts, prompts, tools, evals and durable activities. The
rigour was real but the cost was paid at every handoff: repeated source reads, serialization, review loops, witness
and marker protocols, and thousands of lines of plumbing whose job was to keep agents honest about things a
deterministic check can establish directly.

This design makes the invariants structural instead:

| Property | How it is guaranteed |
| --- | --- |
| Both probes exercise the same real seam | One `run_target(payload)`; the kernel calls it twice |
| The control proves the environment and the seam | Control must hold **and** execute the hypothesis' target lines (coverage) |
| The exploit exercises the reported condition | Exploit must fail with the probe's own assertion **and** execute the target lines; crashes elsewhere are `errored` |
| No mocked target | Structural ban on mocking imports; the auditor rejects doubles that own the property |
| Validity judged without outcomes | A stateless auditor sees hypothesis and probe only, after the deterministic gates |
| Reproducible build | The submitted build script is replayed in a clean container; the producer's workspace is never evidence |
| Attributable failure | A fixed, ordered gate list; every rejection names its gate and reason |
| Two native probes per revision | Two pytest test ids through one driver; JUnit and coverage reports per run |

Independent evaluation of each objective survives without separate agents: each gate is a labelled, countable event.
`ast_guard` measures contract adherence, `build_replay` environment work, `control_*` seam location and grounding,
`exploit_*` hypothesis quality, `blind_audit` validity, and the verdict end-to-end accuracy against the oracle. One
skill file per objective is the unit of improvement.

## Polarity

`holds`: `run_target` returned, the invariant held. `violated`: the probe's own `assert` failed, i.e. the reported
condition occurred. On the vulnerable revision the exploit must be `violated`; on the fixed revision it must be
`holds`. This is the security-regression form (the test fails on vulnerable code). The classification is made by the
kernel's driver from the exception type and the frame it was raised in, cross-checked against the native JUnit
result; a disagreement is `errored`, never decisive.

## Verdict

| Facts | Label | Fix |
| --- | --- | --- |
| vulnerable: control holds, exploit violated, both covered, audit valid | `LIKELY_EXPLOITABLE` (K1) | fixed: control holds and exploit holds → `verified`; else `not_verified` with the reason; no fixed revision → `not_applicable` |
| over the investigation: no K1 submission and at least `negative_threshold` distinct clean negatives (K4 below) | `LIKELY_NOT_EXPLOITABLE` (K4) | `not_applicable`; the fixed revision is not run |
| last gate was `build_replay` | `UNABLE_TO_RUN` (K2) | n/a |
| last gate was `infra` (timeout, container failure, held identity) or no submission | `ERROR` (K0) | n/a |
| budget exhausted at any other gate | `INCONCLUSIVE` (K3) with the last gate and reason | n/a |

The fix never changes a decisive label. A LIKELY_EXPLOITABLE submission on the vulnerable revision stands whatever the
fixed revision shows; a failing fix is `not_verified` with the reason and, within budget, the producer is asked to
correct the probe.

## Clean negatives (K4)

A submission is a **clean negative** when, on the vulnerable revision, the structural guard and the build passed,
control `holds` and exploit `holds`, both runs executed the target lines (missing or unknown coverage never counts),
and the blind auditor accepted the probe when one is configured. The kernel still gates it as `exploit_run` with the
reason "not demonstrated", so the producer tries another payload. Distinct submissions are counted by digest. When
`negative_threshold` of them are observed and no submission is decisive, the run stops early with
`LIKELY_NOT_EXPLOITABLE`. The threshold is operator-owned (`--negative-threshold`, default 2) and is not visible to the
agent. A probe that holds but does not reach the target lines is not a negative: it says nothing about the code.

This is an evidence rule, not a proof of absence. It is implemented and covered by offline tests with scripted doubles,
but it has not been evaluated against a live model, so its precision is unmeasured. The previous design withheld the
label for that reason, and that caution still applies to any claim beyond the pilot set.

## Boundaries kept from the earlier designs

Immutable source identified by a tree digest; a runtime matrix that owns images; hardened containers with
deterministic names, labels and confirmed cleanup; a held identity never reused; network only during build; operator
provider profiles with no fallback; labels and oracles outside agent inputs; model-written code never on the host.
The `Sandboxes` port is the seam for the OpenShell adapter the production deployment needs; the kernel does not care
which backend answers it.

## What is deliberately absent

Temporal, a chain or stage graph, per-stage record types, witness and marker protocols, a reviewer feedback loop,
per-agent prompt-version plumbing, MCP servers, a UI. If any of these earns its way back, it does so against the
pilot's gate ledger and accuracy, not by principle.

## Open questions the pilot should answer

1. Does one producer with gate feedback reach verified probes on the Python corpus at a cost comparable to the
   chain? (`docs/pilot.md`)
2. Which gate rejects most often, and does a skill change move it?
3. Does the auditor reject anything the deterministic gates let through, and how often is it wrong?
4. Is coverage of target lines a sufficient grounding check, or do we need symbol-level evidence (tree-sitter)?
