---
id: PLAN-0057
kind: plan
title: Early stops and actionable setup blockers
status: complete
updated: 2026-10-13
related: [SPEC-0053]
---

# Early stops and actionable setup blockers

## Objective and dependencies

Implement SPEC-0053 on current main 4a75870 in codex/actionable-blockers. Preserve the primary checkout. Runtime selection and environment execution already expose typed failures; use them without wiring unqualified graph boundaries or copying open PR61 changes.

## Steps

- [x] Inspect existing failure producers and brainstorm coverage/limits.
- [x] Add runtime guidance and typed setup diagnostics.
- [x] Enforce terminal setup failure and attach trusted diagnostics to final results.
- [x] Add negative trajectory/attribution checks and compare isolated frozen evaluation.
- [x] Review, full offline guards, runbook, CURRENT and handoff.

## Validation and progress

Baseline: `UV_PROJECT_ENVIRONMENT=/home/al/git/corsair/.venv make eval AGENT=environment`, run `20261013T111411Z-development-scripted`, clean 16/16 at main 4a75870. Final candidate `20261013T111956Z-development-scripted`, dirty implementation on the same base, clean 16/16. Prompt identity environment-v1 to environment-v2-blockers; frozen dataset unchanged. Mean scripted requests 5.25, tools 3.75, commands 1.75 and output tokens 162.25 unchanged; estimated input tokens 1016.25 to 1088.625 from guidance. These are synthetic observations, not live efficiency/accuracy evidence.

Validation: initial existing affected suite 52 passed; new targeted suite initially 74 passed/1 failed because a framework-only fixture used project.dependencies, which the existing detector does not read. Changed that fixture to an admitted optional-dependency declaration; 75 passed. Final additional halt/output/cleanup cases: 78 passed, one existing SDK deprecation warning. `make test-config`: first 1250 passed; later 1252 passed before the final exit-zero cleanup test was added. That final code/test change is covered by the 78 affected checks. `git diff --check` passed. Record guards run after handoff. No live runtime, provider, Temporal service or network qualification performed.

Review: finalizer refuses ready and unsupported after a halt; missing run references cannot conceal a known failure. Exit-zero native infrastructure failures get trusted citeable diagnostic text. Ordinary successful stderr never triggers failure; unknown delivery takes priority over package-manager text. No raw command/output URLs are copied into guidance. Existing private ledgers still contain originals. The current parser's project.dependencies omission is outside this slice; detection follow-up should cover that separately.

## Decisions and next action

First stop at available deterministic evidence; preserve unknown root cause and raw private receipts. Guidance is operator-owned, no autonomous retries or policy weakening. Implement and validate runtime/environment consumers; document other producer boundaries as follow-up, not implemented coverage.

Review follow-up: corrected the budget-only refusal bug with an N-successful-commands plus refused N+1 regression; prior successful readiness is preserved. Recorded the unmeasured live cost of strict terminal failures. Renumbered our spec/plan to SPEC-0053/PLAN-0057 to avoid PR62. PR62 should merge first; this branch then ports diagnostics into its split tool/dependency/finalizer modules and refreshes the toolset digest.

Review validation: initial rename check caught stale spec frontmatter; corrected before publication. Budget-fix affected checks and record checks rerun together; scripted environment remains 16/16.


## PR63 revision after main package integration

User requested both merge blockers be addressed and minor invocation errors be recoverable. Integrated main `759b016` through a merge (preserving existing review commits), porting diagnostics into dependencies.py, validation.py and the one-file-per-tool package from PR62. Budget-only refusal remains nonterminal. SPEC-0053 now supersedes the original strict first-nonzero decision with a maximum-two, explicit, narrow invocation correction allowance; all other failures still stop. No generic repair framework or SDK retry layer was added.

- [x] Port split package and preserve the refused-extra-call regression.
- [x] Add explicit correction contract, operator cap, pending-result guard and negative trajectories.
- [x] Update skill/prompt/toolset identity and retain correction counts in native eval evidence.
- [x] Compare frozen evaluation, run full offline guards, final review and prepare publication to the existing PR.

Initial port check: 74 passed, one expected toolset-digest mismatch; refreshed the pin for the reviewed tool contract. Expanded affected suite: 112 passed (one existing SDK deprecation warning). No live provider/sandbox measurement yet. Prior strict-policy results above are historical, not evidence for live correction quality.

Final review found and closed one additional gap: the previously failed invocation was initially refused only while a correction was pending. It is now refused throughout the attempt, including after recovery. Added regressions for that trajectory and wrapper argument changes: 82 environment/toolset checks passed. `git diff --check` initially found two trailing blank lines from the package port; removed, then clean.

Frozen candidate `20261013T121409Z-development-scripted`: 16/16, compared with previous `20261013T112748Z-development-scripted` at 16/16. Same dataset; means remain requests 5.25, tool calls 3.75, commands 1.75, output tokens 162.25. Estimated input tokens 1088.625 to 1097.875. New observed setup-correction count is zero on these unchanged cases (not a recovery score). Prompt environment-v3-bounded-correction; config environment-eval-v2-corrections; tool digest bfdd901000c3de152f25474869658a1eabf588a19a173fdfb6c7278eb652fc63. No raw evidence committed.

Full offline guards: 1321 passed before the final repeat-after-recovery guard and two new regressions. Final affected suite after that change: 114 passed, one existing SDK warning. Handoff: HANDOFF-0084. No unresolved code finding from the scoped final review; exact-head CI and live correction measurement remain separate checks.

Final record guards: 5 passed. The staged merge diff against old HEAD reports existing CRLF whitespace in main's benchmarks/candidate-cases.csv; that incoming main content is unchanged by this PR. The net PR diff against integrated main passes `git diff MERGE_HEAD --check`.


## Maven correction review follow-up

Accepted the review at bf15d9a: the mvn-to-wrapper exception is unnecessary on admitted Maven images and risks bypassing runtime wrapper-pin admission elsewhere. Removed it; only the bounded pytest-argument exception remains. Merged main 93a0fab, resolving the skill conflict by keeping correction guidance and PR51's junit4 framework guidance. Missing Maven with either unchanged or changed wrapper arguments is covered as a terminal refusal. Prompt identity moves to environment-v4-pytest-correction; tool description/digest updated. Earlier wrapper recovery results above are historical and superseded. No frozen dataset rewrite; the existing production FunctionModel correction tests remain the new-path coverage, distinct from the eight-case frozen eval and any live measurement.

Validation on integrated main 93a0fab: full `make test-config` 1326 passed (one existing SDK warning); frozen candidate 20261013T122747Z-development-scripted 16/16 versus previous 16/16 with unchanged request/tool/command and estimated token means. Net diff against main passes whitespace checks. HANDOFF-0085 records this revision; no live qualification or merge authorization.
