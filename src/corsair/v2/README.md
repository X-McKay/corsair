# Corsair v2

v2 is built beside v1 on the `develop` branch (redesign D6) and replaces it only when it matches v1 on the frozen
eval sets. The design source is the redesign document "Corsair redesign: design, spec and architecture"
(sections 1 to 13, with the amendments in section 13 superseding earlier sections). This file says where each part
lives; it does not restate the design.

## Chain

| # | Stage | Owner | Module |
| --- | --- | --- | --- |
| 0 | Ground | Grounding agent (advisory placeholder; nothing downstream reads its brief) | `agents/grounding/` |
| 1 | Intake | code | `intake.py` |
| 2 | Select | code | `matrix.py` |
| 3 | Investigate | Investigator agent | `agents/investigator/` |
| 4 | Build | Builder agent, then trusted replay | `agents/builder/`, `build.py` |
| 5 | Probe | Control Prober and Exploit Prober agents | `agents/control_prober/`, `agents/exploit_prober/` |
| 6 | Review | Reviewer agent, outcome-blind | `agents/reviewer/` |
| 7 | Execute | code | `execute.py` |
| 8 | Decide | code | `outcome.py`, `rules.py` |

Investigate runs before Build (amendment A1). After the drafts freeze, trusted code runs both probes once on the
vulnerable revision; an author whose probe is `not_run` or `errored` gets its own diagnostics back for one revision
(D3). Authors have no test-running tool.

`contracts.py` holds every type that crosses a stage boundary. `chain.py` composes the stages as plain async
functions (direct mode, used by evals and `corsair-v2 run`); `workflow.py` runs the same functions in one Temporal
workflow per case on three task queues: `model` (one slot), `workspace` and `control`.

## Rules every module keeps

- No branch on language, framework, CWE, issue, CVE, corpus id, repository, fixture or verdict. Language knowledge
  lives only in matrix rows (`deploy/v2/runtime-matrix.yaml`), framework skills (`skills/frameworks/<name>/`) and
  guidance text.
- Exactly two probes per investigated revision: a benign control and a security regression. Native
  parametrisation inside one test is allowed (D9).
- The label comes from the rule table over recorded facts (D4). No model runs after execution.
- A probe's outcome comes from the exit-code map, the start and end marker files and the per-run token (D8).
- Oracles and labels are evaluator-only and never reach an agent input.
- Probes and commands run exactly once; an uncertain outcome is `infra`, never retried.
- Workers never reach the network except for inference; Build may use the network during setup only.
- Missing telemetry is unknown (`None`), never zero.

## Agents

Each agent is self-contained under `agents/<name>/`: `agent.yaml` (native `AgentSpec`), `agent.py` (factory),
`tools.py`, `skills/`, and its eval set under `evals/<name>/`. A factory takes an explicit native `Model` and an
optional `TemporalDurability`, so direct and durable modes share one definition.
