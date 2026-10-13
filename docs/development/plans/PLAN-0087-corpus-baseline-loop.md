---
id: PLAN-0087
kind: plan
title: Repository-owned corpus baseline and improvement loop
status: ready
updated: 2026-10-13
related: [SPEC-0067, SPEC-0044, PLAN-0073, PLAN-0079, ISSUE-0008, IDEA-0009]
---

# Repository-owned corpus baseline and improvement loop

## Objective and dependencies

Establish trustworthy per-language disposition baselines, then improve one demonstrated weakness at a time without overfitting. The canonical procedure is [the corpus improvement runbook](../../runbooks/corpus-improvement-loop.md). It defines 66 development and 16 held-out configurations, reviewed-oracle metrics, bounded parallel work, frozen comparisons and independent example expansion.

The user requested repository storage and merge to main. Publish only documentation in this change. Main at `e84a2bb` does not contain the local finite campaign runner, reporting refinements or Node22 readiness candidate. This plan does not silently merge that implementation. Inspect pending branches/PRs and reconcile actual source before starting dependent work. [ISSUE-0008](../issues/ISSUE-0008-fix-free-product-investigation.md) records the candidate-free admission blocker; pending fixes may supersede it.

The earlier unpublished campaign used PLAN-0085, which now identifies the merged parallel-offline-suite plan on main. PLAN-0087 is the canonical main-branch plan for this work; do not overwrite PLAN-0085 or assume local record IDs identify the same work across divergent branches. Historical private receipts and earlier local handoffs remain historical context; the runbook and source are sufficient to begin a fresh session.

## Steps

- [x] Put the portable loop in a repository runbook with main-compatible links and explicit implementation status.
- [x] Document the negative-run blocker, current index and fresh-session prompt.
- [ ] Reconcile current product/campaign implementations and reproduce the approved-path and output-exhaustion boundaries.
- [ ] Compare the narrow approved-path correction and candidate-free product support in isolated evaluations; preserve paired and missing-evidence behavior.
- [ ] Integrate a finite campaign entry through existing ports with planned-slot identity, split isolation and conservative delivery/cleanup accounting.
- [ ] Obtain a full positive Python disposition, independent negative and development transfer result; retain all failures.
- [ ] Freeze a candidate, review evaluator-owned oracles and progressively account for all 66 development configurations, including unsupported and unrun entries.
- [ ] Compare one measured improvement against the same isolated and Docker cohorts; evaluate untouched transfer separately.
- [ ] Expand with independently reviewed families when the current set no longer exposes weaknesses; preserve original baselines and fresh held-out coverage.

## Validation and progress

Documentation publication based on `e84a2bb`. Main's source was checked for the absent corpus campaign module and existing candidate-free build refusal. Corpus scope remains 42 topics / 82 configurations; repeated attempts do not increase breadth. No new model, Docker or corpus run and no accuracy gain are claimed. Documentation guards passed 5 tests; the full current-main offline suite passed 1,965 tests with one skip and 11 deprecation warnings in 58.98 s. `git diff --check` passed. Details are recorded in HANDOFF-0113.

Candidate-free lane (2026-10-13, [HANDOFF-0117](../handoffs/HANDOFF-0117-candidate-free-investigations.md)): ISSUE-0008 is implemented by open PR #123; a stacked follow-up adds the resolution-criteria checks and `evals.fixture_e2e.run --without-fix`. Offline: 1,977 passed; scripted `chain` 5/5 and `assessment` 54/54 match main. Live Docker positive/negative attempts are unrun.

## Decisions and next action

Start with the runbook and source verification, then up to three isolated worker lanes: shared approved-path contract, candidate-free product support, and one JavaScript or Perl execution/evidence slice. One coordinator initially owns live Docker/model dispatch. Use actual available agent capabilities; no specific desktop app is required.

Each finite execution iteration has at most 24 full investigations; the complete development baseline therefore needs multiple batches. Do not replace unknowns with zero, operational errors with negative findings, or unsupported cases with omissions. Keep held-out cases out of tuning and add reviewed cases by family rather than teaching fixture answers. A missing prerequisite blocks its dependent run, not independent work. Publication of this documentation is authorized; implementation work does not inherit blanket permission to deploy or schedule unattended runs.
