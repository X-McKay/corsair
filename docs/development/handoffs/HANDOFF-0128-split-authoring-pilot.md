---
id: HANDOFF-0128
kind: handoff
title: Split authoring pilot
status: recorded
updated: 2026-10-13
related: [SPEC-0078, PLAN-0093, ISSUE-0009]
---

# Split authoring pilot

## Verified state

Branch codex/probe-validity-evidence remains at unpublished7300a3676597c91729e72863e284fd845c1ef0fe. Dirty workspace contains authoring procedural guidance, evaluation-only property/challenge/split prototypes, tests and records. No new PR, dependency, coordinator or production orchestration change. Preserve unrelated HANDOFF-0118/0119 and their CURRENT paragraph. Previous handoff0127 retains implementation history.

Original six-suite baseline completed on unchanged merged df5c661; final legacy assessment23/54 clean, with26 gate rejections,25 admissions (23 oracle-correct/two conservative) and three task failures. No admitted excessive finding/fix claim in that set. The separate unit-review false approval remains unresolved. No baseline promoted.

Frozen matched joint/split pilot completed four drafts: two related SQL source cases, one repeat each. Same factory, inputs and cumulative budgets; role decomposition is the treatment. Joint10requests/8tools/32270tokens/39.70seconds; split17requests/13tools/53398tokens/79.61seconds. All four pairs failed independent source-only cross-revision validity review: controls require one implementation. Split unsafe-source exploit also asserts malformed SQL. Three other exploits were supported in query-construction scope. Root confirmed source findings and recomputed patch digests. Joint0/2 and split0/2 valid pairs; no generated pair admitted for execution, native outcomes unknown, no application conclusion. This is exploratory evidence, not cross-language/framework/CWE qualification.

## Validation and blockers

Before live launch:65 focused prototype/record tests passed; earlier full production candidate2163passed6skipped. Reviewed repository-owned fixture pair ran both probes on both revisions through existing offline Docker/native-runner ports; correct sensitivity, both cleanups confirmed. Those scripted outcomes are not generated-test qualification.

Evidence is ignored .runs/pr130-live-merged/ and .runs/split-authoring-pilot/{frozen-live-v1,live-v1,blind-review-v1,reviewed-summary-v1.json,scripted-native-v1}. Drivers have completed. Raw evidence must not be published. Read actual report files when resuming.

Execution preparation currently stages only queries.py, omitting captured test_existing.py. No generated pair imports it and source defects are independent, but future admitted execution must stage and bind the complete captured inventory. Do not label an environment omission an author failure. No correction made during the frozen pilot. Property/challenge live comparisons and candidate production live comparisons remain unrun.

## Decisions and next steps

User explicitly says keep the pilot unchanged; pivot to DynamicWorkflow if difficulties persist. Preserve this frozen run and failures. No automatic orchestration expansion based on these defects: they concern control semantics, not proven routing failures. Any next comparison should separately version procedural guidance for stable benign behavior and source-only feedback; do not silently repair measured artifacts. DynamicWorkflow remains the native option to evaluate if adaptive coordination becomes necessary. Qualify its dependency, budgets and durable behavior before production use.

Continue generic unit-test-first design: exactly control and exploit through real production seams, outcome-blind frozen validity, both native outcomes before any conclusion, dependency doubles retaining property logic, optional witnesses. Skills/tool feedback should teach the property rather than add language/CWE-specific policy. Self-hosted endpoint and prior PR authorizations persist; no cost approval needed. Production adoption/publication await measured selection.

## Continuation prompt

```text
Read AGENTS.md, CURRENT, PLAN-0093, ISSUE-0009 and this handoff. Inspect source/git and retained pilot evidence. Use development/review skills. Keep frozen joint/split pilot unchanged. Diagnose stable-control semantics before proposing a separately versioned correction/feedback comparison; do not assume orchestration caused these defects. If persistent adaptive coordination difficulty is demonstrated, evaluate native DynamicWorkflow within existing host gates. Before any supported generated pair runs, bind/stage all captured source files. Keep source-only validity before native execution and require both actual probe outcomes for conclusions. Run affected checks, preserve failed evidence, update records and write a new handoff. Do not publish raw .runs or unrelated records.
```
