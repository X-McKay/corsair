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
- [x] Builder (57), control_prober (65), exploit_prober (70) and chain (`evals/e2e` set `v2`, 100) sets with
  validation fixes; chain scorer (scripted with recorded stage outcomes through the real rules; live via
  `chain.run_case`, refuses without Docker); oracles in proof-of-vulnerability polarity (SPEC-0082 D12) with
  `not_differential` cases; investigator scope cases under the provability rule (91).
- [x] Run-record names in summary.json and policies (`corsair-v2-run/1`; PR #161): `wall_s`, `retries`, `tokens`,
  parameters per attempt (per agent for the chain), status counts; a total with an unknown in it is null.
- [x] Reviewer set (157): built only from accepted prober drafts. Valid pairs are byte-identical to accepted drafts
  (enforced by a test); rejected pairs use accepted previous drafts, the exploit oracles' own decoys (D15, D16) or
  one-edit degradations (stub, copied target, skip, constant, hard-coded marker, adversarial control). No new
  application or exploit code; no safety check stopped it. The first attempt (pre-#153) stays unshipped.
- [ ] Live baseline per agent and language, scheduled through the coordinator; promote, then propose thresholds.

## Validation and progress

- `pytest tests` on a clean checkout of the PR #151 head: 1008 passed, 53 skipped.
- Scripted `evals.run grounding --set development`: 85/85 clean; `evals.run investigator --set development`: 83/83
  clean; each with `--language` narrowing also clean.
- Independent validation (accept/fix/reject): grounding 42/32/0, investigator 73/12/0, builder 16/41/0, chain 66/22/7,
  control_prober 26/34/0, exploit_prober 25/36/0, reviewer 23/50/3 (not shipped).
- Second batch: scripted builder 57/57, control_prober 65/65, exploit_prober 70/70, chain 100/100, investigator 91/91.
- Reviewer: scripted 157/157; gaps: Python 7 valid pairs and no D15 case (two prober families), Perl no
  leading-slash redirect case, no injection aimed at the Reviewer itself, no third-review case.
- Imported corpus: the chain set takes imported pairs through `evals/e2e/from_manifest.py`; the first three
  JavaScript families from `benchmarks/corpus/permissive-reduced/` and the Ruby
  `rubyzip`, `rack-static`, `ruby-git-fetch` and `secure-headers` families bring it to 114 cases
  (scripted 114/114).
- Scripted runs prove plumbing and oracle consistency only. No live run has been made.

## Decisions and next action

- A dimension counts only on cases whose `case.json` declares it, so inapplicable assertions do not inflate rates.
- Language-free behaviours replicated in five wordings measure consistency, not coverage (grounding README).
- Cases that wait on production behaviour sit in a `pending` set, outside every baseline.
- Production gaps found while drafting are relayed to the build owner, not worked around in scorers.
- Next: schedule the first live baseline per agent through the coordinator (HANDOFF-0135).
