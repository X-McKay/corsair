---
id: PLAN-0097
kind: plan
title: Corsair v2 build on develop
status: ready
updated: 2026-10-14
related: [SPEC-0082]
---

# Corsair v2 build on develop

## Objective and dependencies

Build [SPEC-0082](../specs/SPEC-0082-corsair-v2-architecture.md) on the `develop` branch, which was created from main at 14715ea. Every PR targets develop and merges when CI is green; Al authorised this on 2026-10-14 at 08:09Z. Main stays untouched until Al decides to replace it with develop.

The build runs in parallel lanes with Opus sub-agents. It reaches a first goal before any gate resumes: a few correct end-to-end runs across languages, and a baseline for every agent. Design questions and record numbers go through the coordinator to the redesign thread, which is the design authority.

Inputs:

- **Eval corpus:** the #131 eval corpus branch ported to develop rather than merged to main. Its chain cases go to `evals/e2e/`, and its per-agent cases go into each agent package's `evals/`.
- **Images and matrix:** the toolchain images and `deploy/v2/runtime-matrix.yaml`.
- **Grounding placeholder:** Al's description of the ADO intake and grounding agent, attached on 2026-10-14.

Every model call goes to llm.almckay.io. Execution goes through Docker only. Nothing needs kind or OpenShell.

## Steps

Lanes within a phase can run in parallel. A phase starts once the contracts it consumes have merged.

Phase 0, develop setup:

- [ ] Remove v1's `src`, `tests` and eval runners from develop (D11 default). Keep images, the matrix, corpus and benchmark data, and the docs records. v2 lives in `src/corsair/v2` (PR #133) and moved up to `src/corsair` on 2026-10-14 (Al: package move before the main cutover) and declares its runtime dependencies in `[project]`, not in the dev group.
- [ ] Cut develop's PR path to one offline job, `make test-v2`, until something runs end to end (Al, 08:28Z). The v1 suites, the image gate and the qualification and record guards stay runnable by hand. The "Shorter CI with gates deferred" thread owns this step.

Phase 1, contracts and layout:

- [ ] Versioned Pydantic contracts for every stage in SPEC-0082 (Case, GroundingContext and GroundingBrief, Runtime, ProbePlan, Recipe, ProbeDraft, Validity, ProbeRun, Verdict), plus `ArtifactRef`, `usage.json` and the terminal-reason enum.
- [ ] One layout for evals:
  - Port the #131 corpus to develop.
  - Move `benchmarks/cases`, `benchmarks/corpus` and the fixtures into `evals/e2e/<language>/<set>/`.
  - Keep held-out sets frozen by manifest.
  - Give every agent package an `evals/` folder with its baselines and an empty placeholder `release-policy.yaml`.
- [ ] Run-directory writer for `.runs/chain`, `.runs/evals` and `.runs/campaigns`, with `index.jsonl`. Add `corsair report` over any root, and `make eval AGENT= SET= [LANG=] [MODE=]` with the four eval types.

Phase 2, trusted spine without a model:

- [ ] Docker backend of the PydanticAI Workspace interface: ownership labels recorded before creation, resource limits, no network outside Build, and a sweep by label.
- [ ] Run-one-test templates and exit-code maps in the matrix rows. Add the outcome classifier from the SPEC-0082 table and a canary pair per framework skill, run on all seven images.
- [ ] Execute, the rule table R0 to R6, fix verification and the report.
- [ ] Hand-written reference probe pairs for the existing fixtures in Python, Java, Perl, Node and Ruby, each giving its oracle outcome on both revisions.

Phase 3, agents. Each agent ships with its own eval set, a scripted suite and a replay or live suite:

- [ ] Investigator: merges identification and planning; uses search; declares the component.
- [ ] Builder: recipe, trusted replay and the three cache levels.
- [ ] Control Prober and Exploit Prober as separate packages over a shared probe-protocol skill, framework skills, write tool and draft contract. Add the trusted single-run correction step and the review feedback loop (at most three review rounds, two review revisions per author, outcome-blind feedback, re-frozen digest each round).
- [ ] Reviewer: frozen labelled pairs, including copy, mock-the-target and vacuous-assertion traps.
- [ ] Grounding placeholder, behind two ports, each with an in-memory fixture stub:
  - ADO work-item intake: field map, header parser, backfill and skip list.
  - Security graph: the context assembly and citation check.
  - Grounding eval on a fixture graph.
  - No connectivity.

Phase 4, the chain:

- [ ] One Temporal workflow per case and a direct mode over the same stage functions. Three queues, a retry class per operation, artifact references, the correction budget (A2), and `corsair run --id | --issue-json`.

Phase 5, first goal (this lifts the gate deferral):

- [ ] End-to-end runs until at least three reach the correct decisive label on both revisions, in at least three languages.
- [ ] A promoted baseline for every agent: accuracy, latency and tokens by language and eval type.
- [ ] v1 baseline from main through the same scorer; report the chain metrics side by side.

After phase 5, on Al's call:

- [ ] OpenShell Workspace backend, the kind gate, held-out scoring and row upgrades to `live`; then Al decides whether develop replaces main.

## Validation and progress

2026-10-14: develop exists at 14715ea, the same commit as main. This plan and SPEC-0082 are documentation only. No code, model, Docker or cluster run has been made for them.

Each step records its actual commands and results here, including failed attempts. A failure is never replaced by its later successful rerun.

2026-10-14, D18 (branch `claude/v2-d18`): the chain runs a second, blind exploit attempt before R5, reusing attempt 1's control bytes in a new pair with its own digest, exploit-only D3 check and review loop; `rules.decide` reads `attempts` and decides on the last attempt; R5 needs two `assertion_failed` PoVs and carries `sensitivity: unverified`. Scripted only (fake stages and the scripted e2e replay); no live model or Docker run. `uv run --locked python -m pytest -q -n auto tests`: 1722 passed, 55 skipped.

## Decisions and next action

Decisions are recorded in SPEC-0082. Defaults this plan uses until Al decides otherwise:

- D10: the Investigator does not read Grounding output.
- D11: v1 is removed from develop in phase 0.
- R5 lists its calibration without requiring it.

D18 (Al, 2026-10-14 11:26Z) adds a phase 3/4 step: before R5, run one independent second exploit attempt reusing the first control, decide over both attempts, and stamp every R5 `sensitivity: unverified` until the corpus measures LNE precision per language and vulnerability class.

Next action: phase 0 and the phase 1 contracts, in the "v2 build on develop" thread.
