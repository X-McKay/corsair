---
id: SPEC-0078
kind: spec
title: Unit tests at application seams
status: accepted
updated: 2026-10-13
related: [PLAN-0093]
---

# Unit tests at application seams

## Goal and scope

User direction: make native unit tests the default across languages, frameworks and CWEs. No class-specific branch or recorder is required; a claim that depends on external semantics must retain the corresponding integration scope. Exactly one benign control probe and one exploit probe (security safety regression) must execute the real implementation through existing seams on each investigated revision; discovery alone is not execution. Observe outputs, specified exceptions, fixture state or controlled dependency calls. SQL construction can be tested with a recording database double without a database; database-engine semantics still require integration evidence. See the [investigation contract](../../investigation-contract.md).

## Boundaries and design

Planning declares a typed unit observation and its property/seam, with an explicit dependency description when used. Existing effect-witness plans remain readable. Missing instrumentation alone never requires an unsupported unit plan. Source and application behavior remain immutable.

Authoring uses native framework facilities, confined to approved test paths. A double replaces an external dependency at the reviewed boundary, never the implementation or property being tested. Execution retains native discovery, exactly two outcomes, patch/source identities, classified assertion failures, and attributable operational failures.

A fresh pre-execution call of the existing evidence-assessment agent reviews frozen test code, per-revision source, the plan and reported condition without access to receipts, test outcomes or verdicts. Its conclusions about source linkage, condition exercised, assertion relevance and dependency scope are bound by trusted code to the exact observation plan and source. They are model judgments with retained citations, not formal proof or independent runtime attestation. The deterministic gate requires this validity evidence for unit observations; a model-authored pass alone is insufficient. Missing or negative review remains inconclusive for test validity, rather than requiring a low-level recorder. The composition has one validity-producing path through pre-execution review finalization. The later disposition call consumes its immutable result and cannot produce new validity judgments. No new agent, framework, scheduler or language-specific recorder is necessary.

Optional instrumentation remains additional evidence. Contradictions prevent conclusions. Legacy witness plans retain their existing admission rules and qualification history. Unknown execution, wrong source/patch, failed control, skipped tests, unplanned exceptions and sandbox interference never establish safety.

## Acceptance and validation

- Unit plans without recorder facilities are admitted; missing observation, inconsistent modes and unexplained dependency doubles are refused.
- Native controlled-dependency tests call a real SQL-construction function; the same two tests distinguish unsafe concatenation from parameter binding without a database.
- Unit gates accept relevant reviewed assertions and reject absent/negative/stale review, wrong identities, operational failures and contradictory evidence.
- Assessment review is source/patch/condition grounded and executed after authoring and before investigation execution, without result evidence; authors cannot supply their own trusted validity record.
- Compare frozen scripted planning, authoring and assessment evaluations. Add adversarial unit-review checks without relabeling old frozen cases or claiming scripted model quality.
- Shared direct/durable routing uses the same contracts. Live provider semantic calibration and each runtime/framework remain separately qualified; cross-language policy is not blanket runtime support.

## Decisions and open questions

Accepted by the user on 2026-10-13. Existing agent responsibilities suffice: planning states the property, authoring realizes it, assessment reviews its validity and interprets execution, deterministic code limits conclusions. Semantic review quality needs measured live evaluation; unsupported source visibility must be reported rather than guessed.

## Accepted live-evaluation follow-up

The first live unit assessment admitted benign input as an exploit and drafted affirmative reviews of copied/wrong-module targets. User approved a bounded correction: explicit cited findings for each probe’s actual production binding, input/preconditions, assertion and dependency substitutions, with revision validity derived from both probes. Simplify planner native-ID construction at the runner boundary and expose review evidence requirements explicitly. Aggregate actionable contract feedback; do not loosen semantic requirements to obtain clean outputs. Track semantic false approvals separately from contract/evaluator failures and version evaluator corrections while preserving historical measurements. No additional agent or mandatory recorder is introduced. Implementation and live qualification of this follow-up are separate from PR130’s merged status.
