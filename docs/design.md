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
| The exploit exercises the reported condition | Exploit must violate the trusted invariant check **and** execute the target lines; application exceptions are `errored` |
| No mocked target | Structural ban on mocking imports; the auditor rejects doubles that own the property |
| Validity judged without outcomes | A stateless auditor sees hypothesis and probe only, after the deterministic gates |
| Reproducible build | The submitted build script is replayed in a clean container; the producer's workspace is never evidence |
| Attributable failure | A fixed, ordered gate list; every rejection names its gate and reason |
| Two native probes per revision | Two runtime-native executions through one adapter; one test id, JUnit and coverage report per run |

Independent evaluation of each objective survives without separate agents: each gate is a labelled, countable event.
`ast_guard` measures contract adherence, `build_replay` environment work, `control_*` seam location and grounding,
`exploit_*` hypothesis quality, `blind_audit` validity, and the verdict end-to-end accuracy against the oracle. One
skill file per objective is the unit of improvement.

## Polarity

`holds`: the invariant held. `violated`: the trusted invariant check failed, i.e. the reported condition occurred.
On the vulnerable revision the exploit must be `violated`; on the fixed revision it must be `holds`. This is the
security-regression form (the native test fails on vulnerable code). Python probes express a violation by raising
their own `AssertionError`; the driver verifies the deepest traceback frame belongs to the probe. JavaScript, Java
and Perl probes return a boolean and the kernel-owned driver asserts it, so an application cannot disguise its
exception as a violation. Every exception thrown by these probes or their application code is `errored`. Every
adapter cross-checks its driver record against JUnit-shaped test evidence; disagreement or malformed evidence is
`errored`, never decisive. Coverage comes from coverage.py, V8, JaCoCo or Devel::Cover and is normalized before the
same exact-target and target-line gates run.

## Verdict

| Facts | Label | Fix |
| --- | --- | --- |
| vulnerable: control holds, exploit violated, both covered, audit valid | `LIKELY_EXPLOITABLE` (K1) | fixed: control holds and exploit holds → `verified`; else `not_verified` with the reason; no fixed revision → `not_applicable` |
| last gate was `build_replay` | `UNABLE_TO_RUN` (K2) | n/a |
| last gate was `infra` (timeout, container failure, held identity) or no submission | `ERROR` (K0) | n/a |
| budget exhausted at any other gate | `INCONCLUSIVE` (K3) with the last gate and reason | n/a |

`LIKELY_NOT_EXPLOITABLE` is not emitted. A probe that did not demonstrate the condition is evidence about the probe,
not about the code; a negative verdict needs independent attempts and a measured precision, which this pilot does not
have.

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
