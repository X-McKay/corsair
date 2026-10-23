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
| The control proves the environment and the seam | Control `PASS` requires Boolean true **and** exact target-line coverage |
| The exploit observes the reported condition | Exploit `PASS` requires Boolean false; a clean true return is exploit `FAIL`; both need exact target-line coverage |
| Errors cannot become negative evidence | Probe/application exceptions, invalid returns, malformed reports and missing coverage remain nondecisive |
| No mocked target | Structural ban on mocking imports; the auditor rejects doubles that own the property |
| Validity judged without outcomes | A stateless auditor sees hypothesis and probe only, after the deterministic gates |
| Reproducible build | The submitted build script is replayed in a clean container; the producer's workspace is never evidence |
| Attributable failure | A fixed, ordered gate list; every rejection names its gate and reason |
| Two native probes per revision | Two runtime-native executions through one adapter; one test id, JUnit and coverage report per run |

Independent evaluation of each objective survives without separate agents: each gate is a labelled, countable event.
`ast_guard` measures contract adherence, `build_replay` environment work, `control_*` seam location and grounding,
`exploit_*` hypothesis quality, `blind_audit` validity, and the verdict end-to-end accuracy against the oracle. One
skill file per objective is the unit of improvement.

## Boolean observation and role results

Every submission explicitly declares `contract_version="corsair-lite/differential-probe/2"`. Missing or stale
versions are rejected before sandbox construction with instructions to rewrite the probe. No polarity is inferred.
The existing case/request schema is separate and remains `corsair-lite/1`.

All four runtimes use one payload-only invariant through the same setup and real public target call. True means
the security property remained preserved; false means the reported condition occurred. The probe receives neither
its role nor the expected answer. Python requires `bool`, JavaScript requires primitive Boolean values, Java
requires primitive `boolean` or non-null `Boolean`, and Perl accepts only its narrow 1/0/empty-string Boolean form.
Arbitrary truthy values are errors.

The trusted driver expects true for control and false for exploit. Matching the role expectation yields `PASS`;
a clean opposite Boolean yields `FAIL`. Every uncaught exception, including an application assertion, yields
`ERROR`. The remaining individual results are `NOT_RUN` and `INFRA`; neither is a Boolean observation. Public
evidence records `result` and `invariant_held`, without a second outcome vocabulary.

Each adapter cross-checks its strict driver record against one named, non-skipped native test and the process exit
code. Stale records, contradictory polarity and malformed evidence fail closed. Coverage comes from coverage.py,
V8, JaCoCo or Devel::Cover and is normalized before the same exact-target and target-line gates run. Functions,
methods, scripts, CLIs and Java main entry points share this contract. Child-process target execution requires
verified native child coverage; launcher coverage, stdout and exit status alone are insufficient.

## Verdict

| Facts | Label | Fix |
| --- | --- | --- |
| source: control `PASS`, exploit `PASS`, exact target lines covered by both, audit accepted | `LIKELY_EXPLOITABLE` (K1) | Fixed control `PASS` and exploit `FAIL`, with the same decisive prerequisites → `verified`; otherwise `not_verified`; no fixed revision → `not_applicable` |
| source: control `PASS`, exploit `FAIL` with clean true invariant, exact target lines covered by both, audit accepted | `LIKELY_NOT_EXPLOITABLE` (K4), scoped to the reported finding, submitted payload, exact revision and runtime; no claim about other attacks | Fixed revision has its own disposition and derived fix status |
| no source disposition and last gate was `build_replay` | `UNABLE_TO_RUN` (K2) | n/a |
| no source disposition and last gate was `infra` (timeout, container failure, held identity) | `ERROR` (K0) | n/a |
| budget exhausted at any other gate | `INCONCLUSIVE` (K3) with the last gate and reason | n/a |

Both decisive labels require an accepted blind audit; a run without an auditor is nondecisive. A valid exploit
`FAIL` is negative evidence about the tested condition, not a rejected probe. Exceptions, invalid returns, skipped
runs, infrastructure errors, missing reports, uncovered targets and audit rejection cannot establish a negative.

The top-level label mirrors the source revision. Each evaluated revision also retains its own disposition and
reason code, so a fixed-side failure never erases the source result. A removed fixed target file yields
`INCONCLUSIVE/TARGET_REMOVED` and `fix=not_verified`, because the original seam was not executed. Fixed build or
coverage failures also leave the fix unverified. The producer stops after either decisive source disposition; only
a positive source with a correctable fixed-side probe error may retry, preserving the established source label.

`verify` and `investigate` exit zero for either decisive source label, even if a separate fix remains unverified.
Other dispositions exit nonzero; invalid or stale submissions exit 2 before sandbox construction. The evaluator
checks label and fix separately, so a successful command alone does not satisfy a case's expected fix.

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
