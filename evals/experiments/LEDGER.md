# Experiment ledger

Canonical record of every evaluation-gym experiment wave since [PLAN-0003](../../docs/plans/active/PLAN-0003-evaluation-gym.md).
Rounds 1 to 4 of the earlier loop are recorded in [PLAN-0002](../../docs/plans/active/PLAN-0002-improvement-loop-rounds-1-2.md)
and are not repeated here. Only the orchestrator writes this file; worktree agents return telemetry and never commit it.

Rules: every row names the tier, repeats, dataset digest and configuration identity it was measured under; a comparison
across different dataset digests is INCOMPARABLE, never a regression or a win; live numbers are small-n diagnostics on
`Qwen3.6-35B-A3B-NVFP4` via `hosted_vllm/`; nothing here promotes a baseline.

Ideas already rejected in PLAN-0002 and not to be retried without new evidence: running producer and auditor roles
concurrently (control cleanup must precede the adversarial run; container time dominates anyway), and carrying the
complete target module in the producer packet (superseded: the 0/3 producer result was the RootModel output schema).
The tables below are rendered from `ledger.jsonl` by `corsair gym ledger render`; edit the JSONL, not the tables.

## Baselines

| Id | Commit | Tier | Repeats | Dataset digest | Objective J | Macro verified acc | Worst language | Macro eff. tokens | p50 s | Scorecard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ref-w1-tier0 | `0697ff0` | tier0 | 3 | `97fc4873928d` | 1.455 | 1.000 | 1.000 | 37512 | 76.2 | .runs/gym/reference/tier0.json |
| ref-w1-tier1 | `0697ff0` | tier1 | 3 | `ec8cd98558ed` | 1.403 | 0.967 | 0.800 | 37079 | 57.9 | .runs/gym/reference/tier1.json |

## Waves

## Rejected ideas (do not retry without new evidence)

| Idea | Wave | Why it failed |
| --- | --- | --- |
