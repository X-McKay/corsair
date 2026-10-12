---
id: HANDOFF-0040
kind: handoff
title: Narrow issue identification baseline
status: recorded
updated: 2026-10-12
related: [SPEC-0024, PLAN-0024, SPEC-0022, ISSUE-0007, ISSUE-0006, PLAN-0021]
---

# Narrow issue identification baseline

## Verified state

Work began on clean local/remote main at `0f1abab6379f2a9332d1a476552cf4c1ded3d97b`. This snapshot is written with the changes before publication; resolve its published revision with `git log -1 --format=%H -- docs/development/handoffs/HANDOFF-0040-narrow-issue-identification.md`, then verify branch/status/remote. The user explicitly requested pushing completed work to main. No unrelated changes were present at the start.

SPEC-0024/PLAN-0024 implement a separate source-identification factory in the existing issue-analysis package. The model selects a relevant source symbol/location or abstains. Trusted code preserves the entire original issue and materializes an exact citation from successful current-run reads. It does not predict behavior, invent preconditions or deliver a disposition. Native PydanticAI structured output, Pydantic contracts, a mandatory procedural skill and a restricted FunctionToolset enforce this small boundary. Its read tool computes EOF within an 80-line maximum window. Legacy hypothesis/reviewer factories, source tool, provider and Temporal workflow remain unchanged. No new model stage is connected to the durable graph.

The user accepted this narrower role and prioritizes valid final dispositions and evidence over token/latency optimization. The revised draft SPEC-0022 assigns conditional setup and test planning to the planner. The original issue is untrusted task data even when preserved exactly. PLAN-0023's old-role judge prerequisite is cancelled; old labels/failures remain history.

## Validation and blockers

The [qualification report](../../qualification/issue-identification.md) records three separate frozen native-provider candidates at the authorized endpoint. Final v3 completed all 16 attempts (eight development cases, two repeats), with every deterministic assertion passing, no task/evaluator failures, zero unknown tool attempts and zero output corrections. Expected targets and abstentions matched both repeats. This is an exposed development baseline, not a held-out accuracy claim or proof of arbitrary source semantics. No LLM judge is used.

V1 completed 16/16 with raw all-check 7/16: six arbitrary report-excerpt boundary mismatches, one genuine same-name decoy error and two evaluation metric double-count flags. V2 removed report rewriting, refined body/relevance guidance and corrected metric accounting; it completed 15/16 with all completed outputs passing. Its remaining failure was a refused end_line80 request against two lines. V3 removed unnecessary endpoint selection without weakening confinement or retry limits. Prior failures and original reports remain intact.

Private evidence is `.runs/issue-identification-20261012/`: live-001/002/003, separate logs, summaries and source-v1/v2/v3 manifests/copies. Final manifest SHA256 is `ef7bf4ab4da199038c56e9f24cc9e335a8f59639abcd67a9fd201bfda49141e6`; all 25 final source/config/corpus/test inputs and copies matched after execution. Native metrics match receipts. Final usage: 31 requests, 15 successful reads, 44730 input/10163 output/8512 reasoning tokens, 92.065s summed task time, provider/reasoning usage coverage 16/16. Alias discovery is retained; immutable loaded weights and billing remain unknown.

Final code preflight passed 390 offline checks in 6.88s, including 21 focused checks. Earlier offline failures (instruction whitespace expectation and scripted citation endpoint omission) were corrected before their live candidates; logs remain retained. The existing event-loop deprecation warning remains. Final diff review found no unresolved blocker for the isolated baseline; the first final record check caught a renamed mandatory issue heading (1 failed, 3 passed). The heading was restored with historical context in prose; the corrected record/link checks passed 4/4.

No OpenShell, Temporal or historical-project runtime was created by this work. Native HTTP clients close via the provider context manager. No runtime deletion is needed or inferred from this read-only provider work. No new native durable, OpenShell or real-project test execution was performed. All 50 real candidates remain unqualified. ISSUE-0007 remains blocked for end-to-end admission; ISSUE-0006 still gates broader transfers/reconciliation. No policy, TLS, immutable pin, kernel requirement or dependency was weakened. Raw evidence/state/credentials are excluded from publication.

## Decisions and next steps

The bounded identification implementation and provider comparison are complete. Next, independently review fresh localization cases and define/implement the separate read-only planner under SPEC-0022 with deterministic fixture oracles and meaningful negative cases. Qualify direct/durable behavior before integrating it. A native fixture planner/author/executor composition should then retain exactly two identical tests across source variants, actual discovery, controls, expected security assertion failures, application witnesses and attributable cleanup. A localization pass does not qualify those stages.

For a real project, continue PLAN-0021 source/runtime/dependency admission independently, with fresh storage/kernel/CNI/gateway evidence and a nonempty concrete source/test/dependency recipe before execution. Existing synthetic and fixed-source evidence does not admit historical JSPWiki dependencies. Failed controls, skipped discovery, unknown execution and sandbox denial cannot prove a fix. Preserve uncertain delivery and failed attempts; do not blindly replay side effects. Existing authorization covers implementation/testing and periodic tracked commits/pushes, including this main publication.

## Continuation prompt

```text
Read AGENTS.md, README.md, docs/development/CURRENT.md, SPEC-0024/PLAN-0024, revised draft SPEC-0022, ISSUE-0007 and HANDOFF-0040. Use the Corsair development/review skills. Inspect git branch/status/remote and verify the narrow identification source and retained live-003 report/freeze; handoffs are context, not proof. Final development baseline is 16/16, while old hypothesis failures and end-to-end gates remain separate. Build the next bounded read-only planner component with native PydanticAI contracts/skills/toolsets and deterministic fixture oracles; independently review fresh localization cases before qualification claims. Do not connect unqualified durable/runtime stages. Preserve exactly two native tests and actual application witnesses before dispositions. Continue PLAN-0021 admission independently where useful. Prioritize correctness over latency, retain all failed attempts and private evidence, run proportionate checks, review the diff, update records/CURRENT and append a handoff. The user authorizes main commits/pushes after completion.
```
