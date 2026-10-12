---
id: PLAN-0023
kind: plan
title: Issue-analysis rubric coding and skill evaluation protocol
status: in_progress
updated: 2026-10-12
related: [PLAN-0018, SPEC-0023, SPEC-0014, SPEC-0019, SPEC-0021, ISSUE-0007]
---

# Issue-analysis rubric coding and skill evaluation protocol

## Objective and dependencies

Apply [SPEC-0023](../specs/SPEC-0023-native-skill-evaluation-protocol.md) to the `analyze-issue` skill as the first bounded step toward ISSUE-0007, under the objective [PLAN-0018](PLAN-0018-local-issue-analysis-provider.md) still owns. The order is fixed by the spec: code the human findings into per-case rubric labels, calibrate the native judge against those findings, then run a baseline, and only then evaluate skill candidates. The typed precondition contract change proposed for ISSUE-0007 is a separate spec after the baseline exists, so its effect is measured rather than assumed.

Blocked prerequisites: judge calibration and the baseline need the retained outputs under the private run directories and the authorized local endpoint; neither is present in the container that produced the first step. Everything that follows from published findings and installed packages proceeds offline.

## Steps

- [x] Code the failure-class taxonomy and per-case rubric labels from the published independent reviews into `evals/issue_analysis/rubric.py`, and write the four public cases with inputs, oracle and labels as one native `cases.yaml` through `Dataset.to_file`. A test regenerates the file, checks label consistency and confirms labels never enter `case.inputs`.
- [x] Per-attempt label contract (`AttemptLabel`, `attempt_labels.yaml`): one entry per identified retained attempt with output and skill SHA256, reviewed semantic classes, and attempts without typed output kept with their failure layer. The case-level history became `reported_failure_history`, rubric coverage only. Calibration readiness requires both the output hash and the skill hash (PR22 re-review, HANDOFF-0037); partial historical entries still load. Tests cover two attempts of one case with different labels and the exclusion of failed, unidentified and skill-unknown attempts from calibration.
- [ ] Code the remaining published and private review findings as `AttemptLabel` entries from the retained copies, computing each output SHA256, and split them into an exploratory set and a disjoint confirmation set before any judge runs.
- [ ] Add the held-out manifest and `tests/configuration` guard (held-out case hash unchanged; no plan or issue cites a held-out case name) and the `SKILL.md` hygiene guard (frontmatter, length budget, no fixture names, CVE identifiers or oracle strings).
- [ ] Exploratory calibration entry `evals/issue_analysis/calibrate.py`: score the exploratory set with native `LLMJudge` using `judge_rubric`, report agreement and false approvals through `ConfusionMatrixEvaluator` and `PrecisionRecallEvaluator`, then freeze rubric text, judge configuration, metric, threshold, minimum denominators and false-approval limit in the plan.
- [ ] Confirmation: apply the frozen judge once to the confirmation set; accept only if the frozen numbers are met, with false approvals reported separately. A miss reopens rubric coding and requires fresh labels for both sets.
- [ ] Switch `evaluate.py` and `live.py` to `load_dataset()`, delete `fixtures/*.json` and `oracles.json`, add skill-file and baseline-report selection to the live entry, and serialize reports with `EvaluationReportAdapter`.
- [ ] Author the first development and held-out cases beyond the four public ones from the PLAN-0021 captured sources (JSPWiki, Werkzeug, Rack) and synthetic variants, with reviewed oracles and the excerpt licensing discipline. Fold the exposed private holdouts into development.
- [ ] Baseline: current skill, frozen profile, three repeats on development and held-out, retained privately and summarized in the qualification report ledger.
- [ ] Review, records, current index and handoff.

## Validation and progress

Steps 1 and 2 ran in a container without `.runs/` or endpoint access: `tests/agents/test_issue_analysis_rubric.py` passed 4, then 6 checks after the PR22 review response; `make test-config` passed 367 checks in 11.17s with the existing event-loop deprecation warning. The native dataset round-trip (typed inputs, oracle, metadata) was probed against installed Pydantic Evals 2.55.0 before use. No inference was run; no judge agreement number exists yet, so no candidate skill may be scored.

Unrun: private label coding, the held-out guard, exploratory and confirmation calibration, dataset migration, corpus authoring and baseline. The committed `attempt_labels.yaml` holds the one published finding whose attempt is identified; it has no output SHA256 yet, so zero entries are calibration-ready. Known limits: the four public cases are all Python path-traversal variants, so the coded labels cover one language and one issue class; the private fresh and held-out cases of PLAN-0018 are not in Git and were coded only to the extent their findings are published.

## Decisions and next action

PR22 review (owner and Codex) established that a case-level union of findings cannot be ground truth for an individual output; calibration truth is now the per-attempt label, and `reported_failure_history` only records what the rubric must be able to catch. Provider-layer and evaluator-layer classes stay in the taxonomy but outside `SEMANTIC_CLASSES`, and an attempt without typed output can carry no semantic label. The same review separated choosing the judge threshold from confirming it; the steps above keep the two sets disjoint. The generated JSON schema is not committed; the regeneration test is the drift guard. The existing fixture and oracle JSON files stay until step 4 so the current evaluation entries keep working. Next action: code the private review findings as identified `AttemptLabel` entries where the retained copies are available, otherwise the held-out and skill hygiene guards, which need no endpoint. Stop condition: a confirmation run below the frozen threshold or above the frozen false-approval limit stops candidate evaluation and reopens rubric coding with fresh labels.

PR22 merged as `3099ec21b9be0204f64e6f14935aed897d26ba1f` after review of head17413af resolved the remaining skill-identity admission finding. Exact-head offline369/6.45s and head Development guards CI passed; the merge tree matches the tested head. No live calibration or inference ran; ISSUE-0007 remains blocked. See HANDOFF-0038 for continuation.
