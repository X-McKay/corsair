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
- [ ] Add the held-out manifest and `tests/configuration` guard (held-out case hash unchanged; no plan or issue cites a held-out case name) and the `SKILL.md` hygiene guard (frontmatter, length budget, no fixture names, CVE identifiers or oracle strings).
- [ ] Calibration entry `evals/issue_analysis/calibrate.py`: load retained typed outputs from a run directory, score each with native `LLMJudge` using `judge_rubric`, and report agreement with the coded `observed_failures` through `ConfusionMatrixEvaluator` and `PrecisionRecallEvaluator`. Pre-register the agreement threshold from this first run.
- [ ] Switch `evaluate.py` and `live.py` to `load_dataset()`, delete `fixtures/*.json` and `oracles.json`, add skill-file and baseline-report selection to the live entry, and serialize reports with `EvaluationReportAdapter`.
- [ ] Author the first development and held-out cases beyond the four public ones from the PLAN-0021 captured sources (JSPWiki, Werkzeug, Rack) and synthetic variants, with reviewed oracles and the excerpt licensing discipline. Fold the exposed private holdouts into development.
- [ ] Baseline: current skill, frozen profile, three repeats on development and held-out, retained privately and summarized in the qualification report ledger.
- [ ] Review, records, current index and handoff.

## Validation and progress

Step 1 ran in a container without `.runs/` or endpoint access: `tests/agents/test_issue_analysis_rubric.py` passed 4 checks; `make test-config` passed 367 checks in 11.17s with the existing event-loop deprecation warning. The native dataset round-trip (typed inputs, oracle, metadata) was probed against installed Pydantic Evals 2.55.0 before use. No inference was run; no judge agreement number exists yet, so no candidate skill may be scored.

Unrun: the held-out guard, calibration, dataset migration, corpus authoring and baseline. Known limits: the four public cases are all Python path-traversal variants, so the coded labels cover one language and one issue class; the private fresh and held-out cases of PLAN-0018 are not in Git and were coded only to the extent their findings are published.

## Decisions and next action

Labels are coded from the published qualification reports, not from re-reading private outputs, so each `observed_failures` entry is traceable to a sentence in those reports; provider-layer and evaluator-layer classes are retained in the taxonomy but excluded from `SEMANTIC_CLASSES` so they are never counted as skill signal. The generated JSON schema is not committed; the regeneration test is the drift guard. The existing fixture and oracle JSON files stay until step 4 so the current evaluation entries keep working. Next action: the held-out and skill hygiene guards, which need no endpoint. Stop condition: a calibration agreement below the pre-registered threshold stops candidate evaluation and reopens rubric coding.
