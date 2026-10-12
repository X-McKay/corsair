---
id: SPEC-0023
kind: spec
title: Data-driven skill improvement with native evaluation
status: draft
updated: 2026-10-12
related: [IDEA-0003, SPEC-0014, SPEC-0019, SPEC-0020, SPEC-0021, SPEC-0022, PLAN-0018, ISSUE-0007]
---

# Data-driven skill improvement with native evaluation

## Goal and scope

Make changes to an agent's operator-owned procedural skill measurable: a candidate skill is promoted only when a frozen, repeated, paired comparison against the current skill on a held-out set shows the targeted failure class improved and nothing regressed. The first consumer is the `analyze-issue` skill under ISSUE-0007; the protocol applies unchanged to every later agent, starting with `plan-two-tests` from SPEC-0022.

The retained ISSUE-0007 comparisons (six candidates, eight attempts each, finite passes between two and seven, manual review finding defects the evaluators missed) show the gap this closes: the data could not separate a better skill from a luckier run. This spec adds no runner, judge framework, sandbox, harness or dependency. External skill tooling (NVIDIA SkillEvaluator, EvoSkill, SkillsBench) was reviewed and not adopted because each drives a CLI agent harness, brings a second evaluation runner, or lets an agent edit skills; their methodology (paired with/without trials, deterministic oracles before agent runs, focused skills) is taken, their code is not.

## Boundaries and design

**Corpus as native datasets.** Each agent keeps one `evals/<agent>/cases.yaml` written and read with `Dataset.to_file`/`from_file` and its generated schema, replacing the separate fixture and oracle JSON pair. `Case.inputs` is the stage input contract; `Case.expected_output` and `Case.metadata` hold the oracle, the human-coded rubric labels, language, issue class, variant kind (base, paraphrase, confined counterpart, missing source, hostile instructions) and split. The task function passes only `case.inputs` to the agent, so evaluator material never enters a prompt. Issue-analysis and planning cases need saved source excerpts and reviewed oracles only; growing the corpus is not gated by ISSUE-0006 or OpenShell. Target: a few dozen cases per agent across the qualified languages, with the licensing discipline used for the CPython excerpt.

**Splits.** `development` cases may be inspected while editing a skill; `held_out` cases are run once per promotion candidate. A manifest of case name and content hash lives beside the dataset, and a `tests/configuration` guard fails when a held-out case changes or when a plan or issue record cites a held-out case by name. The current exposed holdouts become development cases. No sealed third split until the corpus is large enough to need one.

**Signals, in order of trust.** Deterministic structural evaluators remain gates: contract validity, current-run citation grounding, `ToolCorrectness`, `MaxToolCalls`, `MaxModelRequests`, `HasMatchingSpan`. Semantic scoring uses native `LLMJudge` with a per-case rubric from `metadata` and `include_expected_output=True`, or `GEval` where stepwise criteria read better. The judge is validated before it scores any skill, against labels attached to individual retained outputs (`AttemptLabel`: case, run, attempt, output SHA256, skill SHA256, reviewed semantic classes), never against a case-level union of historical findings; attempts without typed output stay attributed to their provider or contract layer and are excluded. Validation has two separated stages. An exploratory run over one labeled set may be used to choose the acceptance metric, the agreement threshold, the minimum number of labeled outputs and the maximum false-approval rate (judge passes an output a reviewer marked defective), after which rubric text, judge configuration and those numbers are frozen and recorded. A confirmation run then applies the frozen judge once to a separate, untouched set of individually labeled outputs and reports agreement with `ConfusionMatrixEvaluator` and `PrecisionRecallEvaluator`, with false approvals of defective analyses reported separately from overall agreement. Only a judge that meets the frozen numbers on the confirmation set may score candidates; otherwise the rubrics or corpus are fixed and both stages repeat on fresh labels. Per policy, a judge ranks candidates and never approves a disposition; humans adjudicate promotion. The SPEC-0021 reviewer agent becomes a scorer only if the native judge fails calibration, as a custom `Evaluator` wrapping the existing agent.

**Comparison protocol.** One evaluation entry per agent (the existing `live.py` shape) with two added selections: the skill file to deliver and a baseline report to compare against. The factory already reads one skill file; it gains a parameter selecting it, and everything else is frozen: model alias, profile, budgets, schema and tool descriptions, `Agent.override` where a non-skill lever must be held fixed. Runs use `Dataset.evaluate(repeat=3)` at concurrency one; the report's `experiment_metadata` records skill SHA256, prompt and config versions, budgets and provider identity. Reports are serialized with `EvaluationReportAdapter` into the private run directory; the sanitized table in the qualification report is the ledger. `report.print(baseline=...)` and `case_groups()` give per-case deltas; a paired sign count per dimension is the only added arithmetic. A bootstrap interval is added only when two candidates are within noise.

**Candidate discipline.** A candidate targets one coded failure class, states its hypothesis, and is a small diff to one `SKILL.md`. Skill length is a recorded metric. A guard refuses fixture names, CVE identifiers, oracle strings and case-specific predicates in any `SKILL.md`. Skills stay operator-owned Git files; a model may draft a candidate from clustered failures in an ordinary session, and the draft enters the same protocol as a human edit.

**Promotion rule, pre-registered per candidate before its held-out run:** no regression on any security, abstention or confined-counterpart case; improvement on the targeted class under the calibrated judge and confirmed by human spot check; no increase in correction prompts, truncation or unknown usage. Failed candidates stay in the ledger.

## Acceptance and validation

Implementation checks: dataset round-trips through the native file format with its schema; the task function provably passes `inputs` only; the held-out guard fails on a modified or cited held-out case; the skill guard fails on injected case strings; the evaluation entry refuses to run a candidate without a baseline report and recorded metadata; offline `make test-config` passes.

Calibration evidence: the exploratory run and its frozen metric, threshold, minimum denominators and false-approval limit; then the confirmation run on a disjoint set of individually labeled outputs, reported with denominators and the false-approval count, before any candidate run. Protocol evidence: one baseline run of the current `analyze-issue` skill on development and held-out sets with three repeats, retained privately and summarized in the ledger.

Live qualification is separate: a promoted skill is not a qualified agent. ISSUE-0007 resolves only when its own criteria are met on held-out cases under this protocol, and the provider, durable and OpenShell gates stay where they are.

## Decisions and open questions

Native Pydantic Evals 2.55.0 supplies datasets with files and schemas, `repeat`, `case_groups`, baseline rendering, report serialization, `LLMJudge`, `GEval` and the report-level calibration evaluators; the installed API was checked. `Agent.override` cannot swap the Capability, so skill selection is a factory parameter. Open: whether the judge runs on the same local endpoint as the agent under test (cheap, but correlated errors) or a separately authorized model; the default is the same endpoint with the correlation named as a limitation until a second model is authorized. The agreement threshold, minimum denominators and false-approval limit are chosen on an exploratory labeled set and frozen before a confirmation set decides acceptance; choosing and confirming on one set is not pre-registration (PR22 review). The first application plan is recorded against PLAN-0018 and ISSUE-0007.

Later user-directed scope decision: SPEC-0024 uses deterministic curated selection checks for the narrowed identification role, without an LLM judge. This draft judge-calibration protocol is not a prerequisite for that role; PLAN-0023 was cancelled rather than treating its incomplete work as qualified. Historical outputs and labels remain retained.
