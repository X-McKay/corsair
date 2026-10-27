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

### Wave 1

| Experiment | Track | Branch@commit | Tier0 gate | Tier1 gate | ΔJ (t0 / t1) | Token ratio (t0 / t1) | Decision | Lesson |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| h3 | dx | `gym/h3-scorecard-reasoning-markers@f645539` | — | — | — | — | merged `7d637e2` | Observation-only change; re-scoring the tier1 diagnostic reproduced every existing field; python.secret_disclosure had 5 capped-call episodes, 4 exhausted |
| s2 | dx | `gym/s2-ledger-dx-rows@7e150a0` | — | — | — | — | merged `672f9cf` | Offline; 17 tests; existing rows re-render byte for byte |
| s3 | dx | `gym/s3-family-check@b27b8d0` | — | — | — | — | merged `46fcaa6` | Offline; 45 tests; stricter rules surface no violation in the checked-in manifests; gym tiers checked as a pair |
| s1 | dx | `gym/s1-runner-streamline@74910d1` | — | — | — | — | merged `ce197d5` | Offline plus scripted Temporal/Docker; rescoring both references identical; verify record reconciled to the VerifyRecord contract in a73a8ebc |
| s4 | dx | `gym/s4-dataset-intake-draft@875db9d` | — | — | — | — | merged `c88ec3f` | Offline; 25 tests; xxe pair drafted in scratch only; proposed oracles are wide by design and need owner review before any tier |
| h2 | efficiency | `gym/h2-producer-decisiveness@a41fed0` | ACCEPTED | REJECTED (language_regressed, objective_below_threshold; regressed: java, perl, python) | +0.097 / -1.039 | 0.640 / 0.785 | inconclusive | tier0 ACCEPTED (-36% tokens, J +0.097); tier1 REJECTED but java 3/3 and perl 1/3 failed on activity heartbeat timeouts while h1 overlapped (sliced re-run 6/6); python provider_max_tokens rose 2 to 6; clean tier1 re-run pending; the decision-shape sentence alone removed 16 of 17 validation retries on tier0 |
| s6 | dx | `gym/s6-scorecard-identity-operational@8824521` | — | — | — | — | merged `a4ac5cc` | Offline; 39 tests; re-scoring reference and h2 tier1 identical; h2 java/perl confounded by heartbeat timeouts, python regression real; identity line shows producer_prompt and producer_skills changed |

## Rejected ideas (do not retry without new evidence)

| Idea | Wave | Why it failed |
| --- | --- | --- |
