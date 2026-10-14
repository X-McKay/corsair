---
id: HANDOFF-0135
kind: handoff
title: v2 per-agent evals, second batch
status: recorded
updated: 2026-10-14
related: [PLAN-0099, SPEC-0082, PLAN-0097]
---

# v2 per-agent evals, second batch

## Verified state

Branch `claude/eval-corpus-breadth-88ptmq`, merged into `develop` through PR #151 (runner, reporting, grounding,
investigator) and carrying the second batch on top of develop with #152–#154 merged in.

| Eval root | Set | Cases | Scripted run |
| --- | --- | --- | --- |
| `src/corsair/v2/agents/grounding/evals` | development | 85 | 85/85 clean |
| `src/corsair/v2/agents/investigator/evals` | development | 91 | 91/91 clean |
| `src/corsair/v2/agents/builder/evals` | development | 57 | 57/57 clean |
| `src/corsair/v2/agents/control_prober/evals` | development | 65 | 65/65 clean |
| `src/corsair/v2/agents/exploit_prober/evals` | development | 70 | 70/70 clean |
| `evals/e2e` (chain) | v2 | 100 | 100/100 clean |

- Prober and chain oracles follow the proof-of-vulnerability polarity (SPEC-0082 D12, develop #153); the chain set
  includes five `not_differential` cases. Investigator scope cases follow the provability rule (Al, 2026-10-14;
  develop #154). Builder refusals use the typed `blocked` output (#154).
- **The Reviewer has no eval set on develop.** Its drafting worker was stopped twice by a safety check while
  inverting exploit drafts and while parking them; the work was not continued by anyone (coordinator agreed). The
  pre-#153 draft (79 cases) and its converter stay outside the repository.
- Seven redundant no-row chain cases (C and JavaScript runners without a matrix row) remain in set `v2`; removing
  them was refused by a local permission check and needs the owner's word.
- Every corpus case not held out (66 of 82, infosec-harness main@52aa2ac) is a chain case; Ruby has no corpus
  cases and Java three pairs.

## Validation and blockers

- `make test-v2` on a clean checkout of each pushed head; scripted `evals.run` per agent as above.
- Independent validators reviewed every set once (verdict counts in PLAN-0099); fixes applied. Prober and chain
  re-validation after the polarity flip is recorded in the PR that carries this handoff.
- No live run of any agent or of the chain. Scripted runs establish plumbing and oracle consistency only.
- Production gaps found and relayed to the build owner: prober stage does not enforce revision limits; Builder
  dependency locations vs declared installs (eval accepts both); Builder lacks framework guidance; DockerWorkspace
  hides a lost exec stream.

## Decisions and next steps

- A dimension counts only on cases that declare it. Language-free behaviours replicated per language measure
  consistency. Cases that wait on production behaviour go to a `pending` set outside every baseline.
- Live baselines need the shared endpoint (one live user at a time, scheduled through the coordinator) and Docker
  for the chain; then promote per set and propose thresholds.
- Per-run telemetry names will follow the build owner's run-record schema when it lands; summary.json adopts them.
- Reviewer eval authoring waits on the owner's decision.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then PLAN-0099 and this handoff. Verify the eval sets on develop
with `PYTHONPATH=src:. python -m evals.run <agent> --set development` (chain: `--set v2`). Schedule the first live
baseline per agent through the coordinator, run it with --provider-config, promote it, and compare by language.
Do not author Reviewer exploit drafts unless the owner says how. Update PLAN-0099, CURRENT.md and write a handoff.
```
