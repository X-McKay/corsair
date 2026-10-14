---
id: PLAN-0099
kind: plan
title: v2 per-agent eval cases, runner and reporting
status: in-progress
updated: 2026-10-14
related: [SPEC-0082, PLAN-0097, PLAN-0098]
---

# v2 per-agent eval cases, runner and reporting

## Objective and dependencies

Give every v2 agent (SPEC-0082 D1: grounding, builder, investigator, control_prober, exploit_prober, reviewer) and the
chain an isolated eval: frozen cases with name, category, input, expected behaviour and declared dimensions, at least
ten per language where the agent has language-dependent behaviour; one command; comparable metrics by language. Gates
stay deferred (PLAN-0097): release policies are placeholders whose thresholds are null until the first live baseline.
Live baselines need the shared inference endpoint, which has one live user at a time (scheduled through the
coordinator), and Docker for the chain.

## Steps

- [x] Shared runner `evals/agent_eval.py` (native Pydantic Evals; scripted oracle replay or live per-agent model),
  `evals/agent_summary.py` (rollups by language and kind, chain dispositions, policy verdicts), per-agent `evals/`
  inside each package, placeholder `release-policy.yaml` per agent and for the chain.
- [x] Grounding set (85) and investigator set (83 + 2 pending), drafted and independently validated; fixes applied
  (PR #151).
- [ ] Builder (57), control_prober (60), exploit_prober (61), reviewer (76) and chain (`evals/e2e` set `v2`) sets:
  validation fixes, chain scorer (scripted with recorded stage outcomes; live via `chain.run_case`), second PR.
- [ ] Invert exploit-probe oracles to the proof-of-vulnerability polarity (SPEC-0082 D12) once the production skills
  and rules change; add `not_differential` cases to the chain set.
- [ ] Live baseline per agent and language, scheduled through the coordinator; promote, then propose thresholds.

## Validation and progress

- `pytest tests` on a clean checkout of the PR #151 head: 1008 passed, 53 skipped.
- Scripted `evals.run grounding --set development`: 85/85 clean; `evals.run investigator --set development`: 83/83
  clean; each with `--language` narrowing also clean.
- Independent validation (accept/fix/reject): grounding 42/32/0, investigator 73/12/0, builder 16/41/0, chain 66/22/7.
- Scripted runs prove plumbing and oracle consistency only. No live run has been made.

## Decisions and next action

- A dimension counts only on cases whose `case.json` declares it, so inapplicable assertions do not inflate rates.
- Language-free behaviours replicated in five wordings measure consistency, not coverage (grounding README).
- Cases that wait on production behaviour sit in a `pending` set, outside every baseline.
- Production gaps found while drafting are relayed to the build owner, not worked around in scorers.
- Next: land the second PR, then schedule the first live baseline.
