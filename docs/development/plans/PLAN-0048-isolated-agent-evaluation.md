---
id: PLAN-0048
kind: plan
title: Isolated per-agent evaluation on the host
status: in_progress
updated: 2026-10-13
related: [SPEC-0044, HANDOFF-0066, SPEC-0023, SPEC-0028, SPEC-0029, SPEC-0035, PLAN-0038, PLAN-0039]
---

# Isolated per-agent evaluation on the host

## Objective and dependencies

Implement [SPEC-0044](../specs/SPEC-0044-isolated-agent-evaluation.md): every agent has an isolated eval loop (frozen set, one command, recorded baseline, comparable metrics, no cluster), starting with the authoring agent. Independent of the kind cluster. Runs beside the work changing the authoring prompt (v6) and per-stage budgets, which owns `src/corsair/agents/test_authoring/`; this plan touches only `evals/`, the Makefile and records.

## Audit (main at `edaea39`, 2026-10-13)

| Agent | Eval set | One command | Recorded live baseline | Cluster-free |
| --- | --- | --- | --- | --- |
| Identification | 8 development cases | `make eval AGENT=identification` | v3: 16/16 attempts passed every check ([report](../../qualification/issue-identification.md)) | Yes |
| Planning | 6 development, three held-out sets of 6 (all exposed; the first two retired by SPEC-0040) | `make eval AGENT=planning SET=development\|heldout3` | v7: development 11/12, third held-out 17/18 ([PLAN-0044](PLAN-0044-typed-planned-witness.md)); not qualified | Yes |
| Authoring | 6 development cases, no held-out | `make eval AGENT=authoring` | None before this plan: scripted only, live authoring ran only in the sandboxed chain ([PLAN-0039](PLAN-0039-live-witness-and-full-chain.md)) | Yes from this plan (static host runner) |
| Environment | None (unit tests only) | None | None | Not yet: its tool runs setup commands in a preparation sandbox |
| Assessment | 17 development, 7 held-out | `make eval AGENT=assessment SET=development\|held_out` | Pending: live baselines from main not yet recorded ([SPEC-0035](../specs/SPEC-0035-assessment-evals-and-durable-chain.md)) | Yes |
| Chain (composition, not an agent) | 5 reviewed-pair variants | `make eval AGENT=chain` | Live with authoring scripted; fully live only in the sandbox | Yes, except live authoring |

Before this plan each suite had its own CLI, its own evidence path convention and no comparison between runs; baselines lived only as numbers in plan records.

## Steps

- [x] 1. `evals/run.py` and `make eval` / `make eval-baseline`: run one agent's suite, file `command.json`, `evidence/`, `summary.json`, `comparison.md` under `.runs/evals/<agent>/`, append `index.jsonl`, compare with the promoted baseline or previous run of the same set and mode.
- [x] 2. Authoring static host runner (`evals/test_authoring/static_runner.py`) and `static` runner entries in the authoring dataset (now `test-authoring-development-v2`; injected conditions unchanged).
- [x] 3. Authoring live mode: `--provider-config`, `--repeat`, provider receipts, live scoring without the scripted author's own counts, admission facts (`evals/test_authoring/admission.py`).
- [ ] 4. Live authoring baseline on RIG0 (`make eval AGENT=authoring PROVIDER_CONFIG=…`), promote it, record the aggregate here; then the same command for v6 when the prompt work lands.
- [ ] 5. Environment eval: a recorded-observation `SandboxExecution` double replaying captured setup-command receipts for frozen cases (Python and Java manifests from the captured benchmark cases), oracle toolchain, framework, discovery command and required commands; scored for contract, grounding (cited manifest lines), command budget, no network-fetch or policy-editing commands, and the unknown-delivery halt. Then add it to `evals/run.py`.
- [ ] 6. Sandbox replay of host-authored patches: a command that takes `report.json` from a host authoring run and runs each frozen authored patch, without a model, through the SPEC-0032 workspace on the vulnerable and fixed variants, filling in the execution dimensions the host eval leaves unknown. Needs the cluster; batchable and independent of prompt iteration.
- [ ] 7. Authoring held-out set written and reviewed apart from the prompt author, frozen by manifest (SPEC-0023), before the next authoring prompt is judged.
- [ ] 8. Live assessment baselines from main through `make eval`, promoted, once the thread re-running them reports.

## Validation and progress

2026-10-13, cloud container, offline:

- `make eval AGENT=authoring` (scripted): 12/12 clean attempts, every assertion passed, static runs used for the reference realization; second run compared with the first.
- Through `python -m evals.run` with a scratch results root, scripted: identification 16/16, planning development 12/12, planning heldout2 completed, assessment development 51/51, chain 5/5 clean attempts; `environment` refused with this plan's pointer.
- `tests/agents/test_isolated_evals.py`: 10 passed.
- `make test-config`: see the PR.

Unrun: any live run (step 4 needs RIG0 and llm.almckay.io); sandbox replay; environment eval.

Output cap (2026-10-13, Al chose "raise the cap" before tuning prompts): live runs at the 16384-token cap failed mostly on truncation. All 31 planning/assessment truncations were 16384 reasoning tokens with no answer, taking 114–123 s, and the reasoning was largely repetitive (one sample: 176 distinct lines of 1395). Server probe on RIG0 with no other model user: `max_model_len` 131072; `max_tokens` 32768 accepted, `finish_reason=length` at 32768 completion tokens after 234.8 s (~140 tok/s). `LocalModelConfig` now admits 24576 and 32768 and a timeout up to 300 s, and the planning, authoring and assessment eval deadlines and token ceilings leave room for one full-cap response. Cap-16384 runs stay promoted as the reference; the cap-32768 reruns are new baselines whose comparison lists the changed provider and budget. If the loops persist at 32768, try a thinking budget or disabled thinking next.

## Decisions and next action

- The audit-hook check is the authoring stage's own admission rule from the parallel prompt work; the eval reuses it once merged instead of keeping a copy.
- Next: step 4 on RIG0, then step 5.
