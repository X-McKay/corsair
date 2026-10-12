---
id: IDEA-0003
kind: idea
title: Remaining agent graph inventory and build order
status: proposed
updated: 2026-10-12
related: [IDEA-0002, SPEC-0014, SPEC-0017, SPEC-0018, SPEC-0021, PLAN-0018, PLAN-0021, PLAN-0022, ISSUE-0006, ISSUE-0007]
---

# Remaining agent graph inventory and build order

## Problem and evidence

[Architecture](../../architecture.md) fixes a graph of five agents plus deterministic nodes, and [Milestone 6](../../implementation-plan.md) adds them in order: issue analysis, environment, test planning, test authoring, evidence assessment. This record inventories what exists on main `afb75f3` against that plan so the next agent is chosen from evidence rather than from the document order alone. It is a survey, not an authorization; every row below was checked against `src/`, `evals/`, `tests/` and the linked records.

Agent inventory, with the acceptance evidence [evaluation-and-acceptance](../../evaluation-and-acceptance.md) requires before a stage is connected:

| Planned agent | Source state | Evaluation state | Gate before connection |
| --- | --- | --- | --- |
| Issue analysis | Implemented: factory, typed draft/final contracts, `read_source` toolset, skill, provider seam, single-agent Temporal workflow | Deterministic fixture6 cases/30 assertions; live provider repeats retained under ISSUE-0007 | Semantic/consistency gate blocked (ISSUE-0007) |
| Issue evidence review (auxiliary, SPEC-0021) | Implemented: reviewer agent, audit/locator contracts, disconnected direct sequence with one revision | Reviewer live001–003 retained; decision labels correct at live003, entailment errors found by independent review | Isolated reviewer gate not passed; not connected |
| Environment | Not started: no package, contract, skill, tool, eval or record | None | Needs an execution toolset over the qualified ports and a prepared-environment evidence contract |
| Test planning | Not started | None | Read-only; needs analysis plus environment evidence contracts |
| Test authoring | Not started | None | Needs approved test-path writes, bounded execution and a native discovery/runner adapter |
| Evidence assessment | Not started | None | Read-only; needs frozen execution evidence contract and deterministic disposition gates |

Deterministic nodes and shared seams the missing agents depend on:

| Graph node or seam | State | Evidence |
| --- | --- | --- |
| Capture immutable source | `GitSource.capture` and `LocalArtifacts` qualified on the host; no bridge from `SourceSnapshot` to agent inputs (IDEA-0002 package4) | [local source artifacts](../../qualification/local-source-artifacts.md) |
| Capture immutable issue | No issue port or GitHub/Azure adapter; issue text enters only as fixture strings | `src/corsair/ports/` has sandbox, execution, artifacts only |
| Replay setup and verify readiness | Sandbox lifecycle/execution adapters qualified for fixed inert commands; toolchain images qualified; no setup-recipe contract, dependency closure or baseline-test discovery node | [adapter execution](../../qualification/openshell-adapter-execution.md), [toolchains](../../qualification/openshell-toolchains.md) |
| Freeze tests and execute fresh | Manually drafted two-test fixture qualified locally; inert report producer qualified on OpenShell; no native pytest/JUnit discovery adapter, no test-patch application, no case runner (`verify --case`) | [two-test fixture](../../qualification/native-two-test-fixture.md), [bounded test report](../../qualification/bounded-test-report.md) |
| Collect receipts and policy events | Execution/lifecycle receipts with typed native error fields | PLAN-0022 |
| Validate disposition and render report | Not started: no `core/` evidence rules or verdict gates, no Markdown/JSON report renderer | Architecture organization lists `core/`, `composition.py`, `cli.py`; none exist |
| Parent investigation workflow | Not started: only the single-agent `IssueAnalysisWorkflow` base and the fixture foundation workflows exist | `src/corsair/workflows/` |
| Model selection | `LocalModelConfig`/`VLLMProvider` inside the issue-analysis package; no shared port and no Bedrock provider | SPEC-0016 |
| Transfer of nonempty untrusted trees | Blocked | ISSUE-0006 |

Every unbuilt agent is downstream of a deterministic node that is also unbuilt, and real-corpus executions remain zero (PLAN-0021). The order in the implementation plan assumes the environment agent comes next, but that agent is the one whose tools execute commands in a sandbox with untrusted dependencies, which is exactly the boundary ISSUE-0006 keeps blocked.

## Proposal and limits

Build the two read-only agents before the two executing agents, because their inputs can be frozen as reviewed fixtures today and they reuse the issue-analysis template without any new port or live runtime:

1. **Test planning agent.** Inputs: an admitted `IssueAnalysis` and a typed environment-evidence fixture (toolchain identity, discovered baseline test, writable test paths). Output: a two-test specification naming fixtures, real implementation calls, expected behavior per revision, observable witnesses, discovery command and scope limits, per the [investigation contract](../../investigation-contract.md). Authority: `read_source` only. Oracle: the reviewed SPEC-0018 pair supplies one correct plan and the contract's forbidden patterns (constant assertions, mocked sink, denial as fix) supply negative cases.
2. **Evidence assessment agent.** Inputs: `AdmittedTestClaims` from the report consumer, execution/lifecycle receipts, frozen test bytes and source excerpts, each per revision. Output: interpretation, citations, limitations and a proposed execution/finding/fix triple that deterministic gates in a new `core/` module admit or reject. Oracle: the six retained two-test fixture runs plus deliberate failure fixtures (failed control, skipped discovery, unknown delivery, sandbox denial). The gates are the first `core/` code and are needed regardless of the agent.
3. **Test authoring agent.** Needs first a native discovery/runner adapter that applies an approved test patch, runs pytest or JUnit discovery, executes once and emits the SPEC-0017 report from actual results; today that producer is inert. Then the agent gets a write tool confined to approved test paths and a bounded execution tool over the existing execution port. The SPEC-0018 pair is its first correctness oracle.
4. **Environment agent.** Last, after ISSUE-0006 or a reviewed narrower transfer contract admits nonempty source trees and dependency state into a sandbox, and after a setup-recipe and readiness-evidence contract exists. Until then, environment evidence is operator-supplied data.

Shared work that precedes any of them: the `SourceReader` bridge from captured snapshots (IDEA-0002 package4), a per-agent evaluation layout copied from `evals/issue_analysis`, and the first deterministic gates in `core/`. Do not add a graph engine, shared memory or a generic repair loop; each agent keeps its own factory, contracts, skill, toolset and evaluation cases, and direct and durable modes reuse the same factory as SPEC-0015 established. No agent connects to the graph before its isolated evaluation baseline exists, and ISSUE-0007 still governs whether the issue-analysis stage can feed the planner with real-provider outputs.

Complexity cost: four packages shaped like `agents/issue_analysis`, one `core/` module, one runner adapter, one parent workflow. Excluded here: issue-provider adapters, Bedrock, CLI entry points and the analyst pilot.

## Decision

Proposed. The test planning agent is specified in [SPEC-0022](../specs/SPEC-0022-test-planning-agent.md) (draft); the deterministic disposition gates and the evidence assessment agent follow. Each later agent gets its own spec and plan when its prerequisite row above changes state.

Accepted first-stage scope change: SPEC-0024/PLAN-0024 implement an isolated issue-identification replacement candidate. It preserves the reported concern and locates source; the planner now owns conditional setup and the test hypothesis. The inventory above remains the pre-change survey, and the old analyst/reviewer remain disconnected historical implementations until explicit migration.
