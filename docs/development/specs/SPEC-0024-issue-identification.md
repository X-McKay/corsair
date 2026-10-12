---
id: SPEC-0024
kind: spec
title: Narrow issue identification and source localization
status: accepted
updated: 2026-10-12
related: [SPEC-0014, SPEC-0019, SPEC-0020, SPEC-0022, SPEC-0023, PLAN-0018, ISSUE-0007]
---

# Narrow issue identification and source localization

## Goal and scope

The user accepted narrowing the analyst to identifying the reported security property and locating the relevant implementation, prioritizing valid end-to-end evidence over latency. Its handoff answers what reported boundary to test and where to investigate. It does not predict execution, prove a vulnerability, enumerate environmental preconditions or issue a finding/fix verdict. The planner retains responsibility for setup, required safe behavior, exactly two tests and observable witnesses; execution and deterministic disposition gates retain their existing obligations.

This bounded implementation is an isolated replacement candidate in the existing issue-analysis component. The hypothesis factory, auxiliary reviewer, existing Temporal workflow and historical evaluations remain unchanged and disconnected from this new output. No unsafe structural conversion between old and new outputs is provided. Connection requires separate planner and direct/durable qualification.

## Boundaries and design

Reuse the immutable bounded `IssueAnalysisInput`, existing saved-source confinement and explicit native provider and PydanticAI structured output function. Keep a separate factory and typed `IssueIdentificationDraft`/`IssueIdentification` in the component, with its own `identify-issue` skill and prompt/config identities. No new scheduler, tool authority, output parser or library-semantic engine is needed.

A ready draft selects one `target`: the local source symbol plus a saved-file reference. The final function verifies authorized scope, current-run successful read coverage and the symbol's presence in the selected source; it attaches exact source quotation and the complete original `reported_issue` from trusted input. Report text remains an allegation or requirement, not established application behavior. The model never generates or trims report text. A missing-information or unsupported result carries one concrete reason and no target; trusted code still preserves the report. Unknown fields, including verdicts, are refused. Fixture identity/oracles never enter model prompts.

The input may describe multiple locations, but this first slice locates one relevant component or abstains when one cannot be established. Guards do not make localization unsupported: guarded and unguarded variants should identify the same reported property and implementation. Dependency behavior and runtime facts are not needed merely to identify that target. Prompt injection in source/report cannot change the task or tools.

## Acceptance and validation

Native FunctionModel tests cover current-run reads, source/scope mismatch, invented tools, no source, unknown fields and honest abstention. An evaluator-owned frozen corpus checks status, exact trusted report preservation, symbol/path and approved source ranges; all expectations stay outside task inputs. Each assertion reports its own dimension. Counterexamples must fail: rewritten report, wrong symbol/path, unrelated source range and wrong abstention. This deterministic benchmark validates selection on curated cases, not arbitrary semantics on unseen projects. No LLM judge is involved.

Measure completion, exact selection, source provenance, repeat consistency, tool/model counts, tokens and failures separately. Scripted fixtures are plumbing evidence only. A finite native-provider smoke run, if performed, uses explicit frozen budgets and no task retries; retain all messages/receipts and uncertain requests. Neither result qualifies downstream composition, production disposition accuracy or closes ISSUE-0007. Broader fresh cases and native durable tests follow separately.

## Decisions and open questions

The user's narrowing supersedes the proposed LLM-judge calibration prerequisite for this new role. PLAN-0023's old-contract labels and failed runs remain history; they are not regraded as passes. No additional model agent is connected in this slice. Whether broader reports require multiple targets is deferred until an observed case justifies it. The first candidate asked the model to select report excerpts. Its frozen smoke exposed arbitrary sentence-boundary mismatches, so candidate v2 removes that task entirely: the trusted finalizer preserves the complete input issue. The original report/oracle remain retained, not rescored as passes. Localization expectations are unchanged across candidates; the new skill instructs checking a candidate body rather than accepting a matching name alone. Evaluation counters use separate observed_* names so native request metrics are not doubled.

The v2 smoke exposed one invalid read request (end_line80 on a two-line file). V3 uses a stage-owned native FunctionToolset over the same bounded saved-source reader: `read_source(path, start_line=1)` returns at most80 lines, computing the actual end at EOF. Paths outside the inventory and invalid starts remain refused, no host access is added, and tool retries stay0. Returned exact line ranges still govern citations. The legacy analyst reader is unchanged. This removes an unnecessary model choice without adding authority or weakening a gate.
