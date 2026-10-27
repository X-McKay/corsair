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
| ref-w2-tier0 | `0697ff0` | tier0 | 3 | `97fc4873928d` | 1.483 | 1.000 | 1.000 | 37512 | 76.2 | /home/al/git/corsair/.runs/gym/reference/tier0.json |
| ref-w2-tier1 | `0697ff0` | tier1 | 3 | `ec8cd98558ed` | 1.411 | 0.967 | 0.800 | 37079 | 57.9 | /home/al/git/corsair/.runs/gym/reference/tier1.json |

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
| s5 | dx | `gym/s5-run-lock@885d0a7` | — | — | — | — | merged `2ecb728` | Scripted Temporal integration proof that a second run waits; Docker suite deferred until the live runs end |
| h1-tier1 | accuracy | `gym/h1-reasoning-cap@55c70ea` | — | REJECTED (objective_below_threshold) | — / -0.176 | — / 1.070 | rejected | Target met: provider_max_tokens 2 to 0, python verified 0.8 to 0.9, macro verified 0.983, no regression, tokens 1.07x; REJECTED on objective only (J -0.176) because 5 trusted-probe ERROR episodes after audit ACCEPT (the payload-raises-before-target defect, h4) score -0.5 each; retest after h4 |
| h2-tier1 | efficiency | `gym/h2-producer-decisiveness@a41fed0` | — | REJECTED (language_regressed, objective_below_threshold; regressed: python) | — / -0.222 | — / 0.956 | rejected | java and perl recovered fully (heartbeat timeouts were operational); python regressed 0.8 to 0.6 on its merits (provider_max_tokens 4, probe ERROR 5); tokens only -4%; the stop-criteria text is rejected; the decision-shape sentence alone (validation retries 16 to 1 on tier0) becomes h2a |

### Wave 2

| Experiment | Track | Branch@commit | Tier0 gate | Tier1 gate | ΔJ (t0 / t1) | Token ratio (t0 / t1) | Decision | Lesson |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| h4 | accuracy | `gym/h4-probe-error-classification@0b1b600` | — | — | — | — | rejected | Premise false: raw receipts show the bound line covered in 19 of 20 mappable adversarial-ERROR episodes; the not-executed picture came from the verifier error path discarding receipt coverage. The narrow rule is a no-op; a wider rule (target-side exception outside allowed exceptions becomes INVALID) is an evidence-policy ruling for the owner |
| h2a | efficiency | `gym/h2a-decision-shape@873a8c5` | ACCEPTED (objective_below_threshold) | REJECTED (language_regressed, objective_below_threshold; regressed: python, ruby) | -0.111 / -0.600 | 0.974 / 0.985 | rejected | Validation retries 16 to 4 (tier0) and 41 to 17 (tier1) but tokens only -2.6% / -1.5%; tier1 regressed python (provider_max_tokens 2 to 5) and ruby (2 of 3 execution_error, evidence_unverified); J is dominated by target-side exception ERRORs and reasoning-cap exhaustion, both prerequisites |
| s7 | dx | `gym/s7-verify-score-nits@890616e` | — | — | — | — | merged `6c4228b` | Offline; 9 tests; gates on gym/loop after merge: check clean, 1345 tests, Docker 61 passed |
| s8 | dx | `gym/s8-target-exception-reward@b97a592` | — | — | — | — | merged `7ab7235` | Offline; 27 tests; reference re-scored in place; h1 still REJECTED on the J margin alone (single-case languages make one ERROR cost ~0.085 J), so track-specific gate criteria follow (s9) |
| w2 | dx | `gym/w2-error-observation-coverage@008fdc0` | — | — | — | — | merged `4593c93` | Verdict-neutral: 425 stored rounds under old and new code, 0 differences in validate_saved, decide, session_verdict; 32 of 38 stored ERROR roles are target_exception with the bound line covered; Docker 61 passed, Temporal 57 passed in the worktree |
| s9 | dx | `gym/s9-track-gate@471a9bd` | — | — | — | — | merged `d67c83d` | Offline; h1 decisive run ACCEPTED under accuracy track (macro +0.0167, tokens 1.070, no regression), REJECTED under objective; h2 clean REJECTED under efficiency; c r0 SandboxExecutionError now operational |

## Rejected ideas (do not retry without new evidence)

| Idea | Wave | Why it failed |
| --- | --- | --- |
| h1 decisive tier1 at thinking_token_budget 4096, no overlapping runs | 1 | Target met: provider_max_tokens 2 to 0, python verified 0.8 to 0.9, macro verified 0.983, no regression, tokens 1.07x; REJECTED on objective only (J -0.176) because 5 trusted-probe ERROR episodes after audit ACCEPT (the payload-raises-before-target defect, h4) score -0.5 each; retest after h4 |
| h2 clean tier1 re-run, no overlapping runs | 1 | java and perl recovered fully (heartbeat timeouts were operational); python regressed 0.8 to 0.6 on its merits (provider_max_tokens 4, probe ERROR 5); tokens only -4%; the stop-criteria text is rejected; the decision-shape sentence alone (validation retries 16 to 1 on tier0) becomes h2a |
| Classify a completed adversarial run that did not execute the bound target as INVALID instead of ERROR | 2 | Premise false: raw receipts show the bound line covered in 19 of 20 mappable adversarial-ERROR episodes; the not-executed picture came from the verifier error path discarding receipt coverage. The narrow rule is a no-op; a wider rule (target-side exception outside allowed exceptions becomes INVALID) is an evidence-policy ruling for the owner |
| Producer response-shape sentence only (no top-level reason; plan carries objective, next_steps, reason) | 2 | Validation retries 16 to 4 (tier0) and 41 to 17 (tier1) but tokens only -2.6% / -1.5%; tier1 regressed python (provider_max_tokens 2 to 5) and ruby (2 of 3 execution_error, evidence_unverified); J is dominated by target-side exception ERRORs and reasoning-cap exhaustion, both prerequisites |
