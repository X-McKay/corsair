# PLAN-0001: pilot plan and open decisions

Corsair validates a reported security finding with two Google ADK agents over a deterministic, coverage-gated kernel, with each agent episode run as one Temporal activity. This record states what the pilot implements, the decisions taken for the pilot, the gates that have and have not run, and the items still awaiting the project owner. The [architecture overview](../../architecture/overview.md) and [ADR 0004](../../architecture/decisions/0004-payload-pair-and-coverage-gated-verdict.md) are the design authorities; this page tracks state.

## What the pilot implements

- **Producer agent** (`agents/producer/`): read-only `read_file`/`list_files` over an admitted immutable snapshot plus the role-filtered skills toolset. Returns a `ProducerDecision`: a `Submission` holding one benign/exploit payload pair as JSON, or an explicit abstention. Never runs code, never writes a probe, never sees an outcome.
- **Auditor agent** (`agents/auditor/`): no tools, native structured `AuditResult`, outcome-blind, reject-only.
- **Kernel** (`policies/verdicts.py`, `steps/verification.py`, `workflows/investigation.py`): gates in the fixed order `target_binding`, `ast_guard`, `build_replay`, `control_run` + `control_coverage`, `exploit_run` + `exploit_coverage`, `evidence_agreement`, `blind_audit`, `fixed_differential`; verdict table producing `EXPLOIT_DEMONSTRATED`, `EXPLOIT_NOT_DEMONSTRATED`, `INCONCLUSIVE`, `UNABLE_TO_RUN`, `ERROR`.
- **Ports and adapters**: typed inference, source-snapshot and sandbox ports; ADK, local-source, Docker, filesystem and Temporal adapters. The sandbox port is answered by Docker only.
- **Evaluation**: isolated producer/auditor evaluation (`just eval-agent`), durable dataset evaluation (`just eval`), frozen datasets under `evals/datasets/` including the independent paired corpus and per-language chain rows.
- **Tooling**: `just check` (Ruff lint/format, Just format, ty, docs links), `just test` (offline), `just test-docker`, `just test-temporal`, `just test-live`, `just verify`, `just eval`, `just eval-agent`.

## Decisions taken for the pilot

| Decision | Taken | Rationale |
| --- | --- | --- |
| Producer output | Payload pair as JSON data; the kernel owns the recipe and materializes the probe at run time | Standing rule: an agent never authors executable exploit code. Keeps assertion authorship with the operator-reviewed recipe. |
| ADK/Temporal integration | One ADK episode per ordinary Temporal activity, single attempt | Keeps the workflow deterministic and the side-effect boundary explicit; the ADK Temporal plugin is experimental and would move the failure boundary ([ADR 0001](../../architecture/decisions/0001-sdk-owned-durable-rounds.md)). |
| Sandbox | Keep the `SandboxPort`; Docker adapter only; OpenShell adapter deferred, not stubbed | An empty adapter misrepresents capability; the port keeps the seam open. |
| `negative_threshold` | 2 independent producer sessions for `EXPLOIT_NOT_DEMONSTRATED` | A single producer miss must not become a negative certificate. |
| Coverage | Exact target-line coverage required in both runs of every pair | Primary guard against a false `EXPLOIT_NOT_DEMONSTRATED`. |
| Languages | Python is the running runtime; JavaScript, Java, Ruby and Perl rows are carried in the corpus matrix only | One qualified runtime; corpus rows preserve the matrix without claiming support. |

## Gates and environment

The cloud development environment has no Docker daemon, Temporal service or model endpoint; it runs `just check` and `just test` only. `just test-docker`, `just test-temporal`, `just test-live`, `just eval` and `just eval-agent` with a live provider run on a dedicated rig. Record each rig run here with its command, revision and result; an unrun gate stays listed as unrun.

| Gate | Where | Status |
| --- | ---: | --- |
| `just check` | cloud | run per change; the docs link check is part of it |
| `just test` | cloud | run per change |
| `just test-docker`, `just test-temporal` | rig | not yet recorded |
| `just test-live`, composed live batch | rig | not yet recorded |
| Isolated producer/auditor baselines on the six labels | rig | not yet promoted |

## Open decisions awaiting the owner

1. **OpenShell adapter timing.** The sandbox port is in place and Docker answers it. When, if at all, to add and qualify an OpenShell adapter.
2. **Probe module versus payload pair.** The pilot keeps the payload-pair contract because the standing rules forbid agent-authored executable exploit code. If the owner wants the producer to write a probe module instead, that rule changes first and [ADR 0004](../../architecture/decisions/0004-payload-pair-and-coverage-gated-verdict.md) is revisited.
3. **Per-call Temporal plugin versus one episode per activity.** The pilot runs one ADK episode per activity. Adopting the ADK Temporal plugin needs a separate decision, conformance review and qualification.
4. **`negative_threshold`.** Set to 2 for the pilot. Raising it costs more sessions per negative; lowering it to 1 is not acceptable under the false-negative rule.
5. **Perl corpus licence.** The Perl rows under `evals/datasets/chain/perl/` need a licence decision before they are treated as redistributable corpus material.

## Blockers

None internal to this plan. Live gates wait on rig time; no decision above blocks offline work.
