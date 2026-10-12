---
id: SPEC-0021
kind: spec
title: Bounded issue-analysis evidence review
status: accepted
updated: 2026-10-12
related: [PLAN-0018, ISSUE-0007, SPEC-0020]
---

# Bounded issue-analysis evidence review

## Goal and scope

Address the observed omitted necessary conditions and valid-but-irrelevant citations in ISSUE-0007 through an independently qualified, read-only evidence reviewer. Root owns integration and runtime mutations. This is a bounded internal issue-analysis stage change, not another top-level investigation stage or a generic repair framework. The deterministic output function establishes provenance, not semantic entailment; repeated prompt/budget changes alone have not established consistency.

## Boundaries and design

Use a separate native PydanticAI Agent with immutable Pydantic inputs (authorized issue/source inventory and completed analysis), its own procedural skill, the existing restricted source FunctionToolset, and a typed review: supported, needs_revision, or insufficient_evidence. Findings identify fields, concrete defects and current-run source references. The reviewer may neither rewrite the analysis nor execute commands. It treats the candidate, issue and source as untrusted data. A supported missing-information result is distinct from a ready result admitted for drafting.

Keep each invocation's requests, reads, usage, timeout, messages and failures separately attributable. Do not call another model inside the analyst's structured output function. Native output validation remains deterministic; no evaluator labels or reference answers enter either agent. No fallback model, serving deployment change or inferred immutable weights identity.

The isolated live001 reviewer missed the same necessary-condition defect twice. Its next candidate adds an observable bounded condition audit: operation, required condition, explicit/entailed/missing coverage and concise basis. A supported ready review requires a nonempty audit; identified missing conditions require a revision finding. These structural invariants cannot prove that the model enumerated every condition. The general skill therefore asks whether the stated conditions can hold while an ordinary operation requirement prevents the claimed effect; independent positive/negative evaluation remains mandatory. See the [retained qualification results](../../qualification/issue-analysis-evidence-review.md).

Qualify the reviewer alone before connecting it. If its isolated gate passes, evaluate one explicit analyst → reviewer → conditional single analyst revision → final reviewer sequence. Revision gets only typed review feedback, original input and candidate; it must re-read evidence. Unsupported review, missing evidence, budget exhaustion or failed invocation blocks downstream work. Do not automatically repeat failed/uncertain requests. The existing single-agent Temporal workflow remains unchanged and does not acquire this qualification.

## Acceptance and validation

Offline tests exercise invalid status/findings combinations, current-run grounding, absent-source handling and skill/tool/schema delivery. Independently authored inputs and separate oracles are frozen before live runs. The isolated reviewer needs two completed repeats of balanced correct/incorrect candidates with accurate decisions, grounded meaningful findings, no false alarms on adequate component assumptions, and no authority expansion. Native Pydantic Evals reports and independent source/output review are required; lexical predicates alone are insufficient.

Only after that gate, run two repeats of original regression contrasts and fresh independently authored cases through the fixed composition with finite budgets. Require supported, semantically adequate outputs; missing source must remain blocked for drafting. Preserve initial defects, review mistakes, revisions, failed attempts and unknown usage. Measure latency, calls, tokens and coverage without treating unreported telemetry as zero. A review approval is a bounded model judgment, not execution or proof of a fix.

OpenShell admission, historical project dependencies, real-provider durable execution and production reliability remain separate gates. A subsequent model-authored synthetic two-test run can demonstrate drafting/execution integration; it cannot qualify any of the 50 real corpus cases.

## Decisions and open questions

The user's explicit direction prioritizes functioning end-to-end behavior over optimization and authorizes this bounded implementation and finite inference evaluation. Architecture permits an additional agent for a concrete failing case with a named owner and measured benefit; these semantic failures justify evaluating this auxiliary reviewer. Native sequential composition and output functions are supported by the pinned SDK and [upstream patterns](https://pydantic.dev/docs/ai/guides/multi-agent-applications/). No bespoke scheduler or shared mutable memory is needed. Reviewer false positives and correlated model errors are explicit evaluation risks.
