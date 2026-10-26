---
name: corsair-gym-loop
description: Run one wave of Corsair's evaluation-gym improvement loop from any agent harness (Claude Code, Codex, a scheduled task): reference run, diagnosis, isolated worktree experiments, deterministic gate, integration, fixture capture and ledger. Use for automated or assisted improvement of accuracy, tokens and latency; it does not change evidence rules or runtime permissions.
---

# Corsair evaluation-gym loop

One wave, driven by CLI exit codes so no harness reproduces a judgment. Design and rules: [PLAN-0003](../../../docs/plans/active/PLAN-0003-evaluation-gym.md), [AGENTS.md](../../../AGENTS.md), [evaluation rules](../corsair-evaluations/SKILL.md). Toolchain is `nix develop -c just …` from a synced worktree; live settings are `.state/settings.json` on the `hosted_vllm/` route; gym runs use the Temporal namespace `corsair-gym` and never `default`.

## Roles

- **Orchestrator** (one per wave): writes briefs, runs gates, merges, captures fixtures, appends the ledger. Only this role writes `evals/experiments/ledger.jsonl`, `LEDGER.md` and the plan record.
- **Auditor** (read/run only): runs tiers, clusters `failure_stops`, proposes 2 to 3 hypotheses with disjoint file scopes after checking the rejected table. The only role besides the orchestrator that sees tier2 (holdout) per-case results.
- **Experimenter** (one per hypothesis, own worktree cut from the integration branch): one bounded change in its exclusive file scope; never edits oracles, fixtures, manifests, budgets, the ledger or the plan; never sees tier2.
- **Case miner** (separate wave from prompt tuning): proposes `request.json` and `Oracle` files through intake; the owner reviews every oracle before it is frozen into a tier.

## Wave

1. Reference. If the ledger has no reference row for the integration HEAD: `just -- gym-run tier0 --repeats 3` and `just -- gym-run tier1 --repeats 3`; `just -- gym-ledger append --kind reference …`.
2. Diagnose. Auditor returns failure clusters by kind and gate, token and time outliers (`corsair gym replay RUN CASE`), and hypotheses `{id, track, target metric, mechanism, files}` with pairwise-disjoint files.
3. Experiment. Per hypothesis, in its worktree: `nix develop -c just sync`, failing test first, change, `just test`, `just check`, plus `just test-docker` for sandbox/driver/image scopes and `just test-temporal` for workflow scopes; then `just -- gym-run tier0 --repeats 3`; if `just -- gym-gate REF CAND` is not REJECTED, `just -- gym-run tier1 --repeats 3` and gate again. Commit as `exp(<id>): <summary>`; return branch, commit, gate table, commands with counts, identity change, unrun gates.
4. Gate. `corsair gym gate --baseline REF --candidate CAND`: exit 0 ACCEPTED, 1 REJECTED, 2 INCOMPARABLE. Accuracy track also needs tokens ≤ 1.10×; efficiency track needs ≥ 10 % lower macro effective tokens or p50 seconds with no language regression.
5. Integrate. Merge accepted branches `--no-ff` into the integration branch one at a time, re-gating each later branch against the new HEAD; re-run tier0 on HEAD and record it as the new reference. Remove rejected worktrees after logging the lesson.
6. Capture and record. `just -- gym-capture RUN CASE` for every failed or flipped case (fixtures are the fast, model-free guard); `just -- gym-ledger append …` per experiment; `just -- gym-ledger render`; append commands and outcomes to the plan record, naming what was unrun.

## Invariants

- Same dataset digest, budgets digest and repeats on both sides of a gate; anything else is INCOMPARABLE, never a win or a regression.
- Any prompt, schema, budget, driver, image or model change is a new configuration identity; say so in the ledger row.
- Missing usage stays unknown; ERROR, UNABLE_TO_RUN and INCONCLUSIVE are never negatives; a failed reproduction never yields EXPLOIT_NOT_DEMONSTRATED.
- No second agent loop, scheduler, tracing stack or replay engine; no model-authored execution; no oracle or outcome in agent, tool or workflow inputs.
- One shared model endpoint: compare latency at equal concurrency; `cpu_seconds` is the contention-resistant figure.
- Nothing is promoted and nothing is pushed without the owner's instruction.
