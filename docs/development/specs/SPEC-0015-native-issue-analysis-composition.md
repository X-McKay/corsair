---
id: SPEC-0015
kind: spec
title: Native issue-analysis fixture composition
status: accepted
updated: 2026-10-12
related: [PLAN-0017, SPEC-0013, SPEC-0014]
---

# Native issue-analysis fixture composition

## Goal and scope

Exercise the existing read-only issue-analysis factory/contracts in direct and native Temporal modes with fixture models. This is priority 1A in the user's authorized four-priority continuation of HANDOFF-0024. Follow [architecture](../../architecture.md), [recovery](../../execution-and-recovery.md) and [evaluation](../../evaluation-and-acceptance.md). No real model request, OpenShell operation, full graph or finding/fix conclusion belongs to this slice.

## Boundaries and design

Use native PydanticAI 2.55.0 `TemporalDurability`, `PydanticAIWorkflow`, `PydanticAIPlugin` and replay-safe `LogfirePlugin`, with Temporal SDK 1.34.0 and the existing verified CLI 1.9.1/service 1.32.0. Reuse `create_issue_analysis_agent`, `IssueAnalysisInput`, `IssueAnalysis`, fixture dependencies, prompt, tools, output validators and native usage limits. The factory gains only an operator-injected native durability capability, coordinated with its owning agent; domain contracts remain independent of Temporal.

Source provides one small native workflow base; the test-only top-level concrete workflow binds the same factory-built fixture agent. Native registered model keys select trusted worker fixture models. Expected labels/oracles remain in evaluator/test worker configuration and never enter agent prompts or run dependencies. No dynamic scheduler, provider wrapper, model protocol or opaque whole-agent activity is introduced.

Every model/tool operation uses native durability. For this finite fixture qualification, activity retries are explicitly limited to one, with bounded timeouts, and agent correction retries remain separately identified. Restricted read authority and current-run quotation/scope admission remain the existing factory's responsibility. Native model/tool/contract/limit failures preserve their native cause chain; failure is never converted into a successful analysis. Fixture token usage is estimated and has no provider billing meaning.

Local telemetry uses native instrumentation and supported LogfirePlugin with sending disabled and an in-memory OpenTelemetry exporter. Configure it before native clients/workers/replayers, keep source content excluded, and preserve sanitized span identities/counts locally. A replay must produce no additional model/tool execution spans. No hosted telemetry account or custom tracing implementation is required.

## Acceptance and validation

- Same explicit agent instance/factory and saved inputs produce matching typed direct/durable fixture outputs, tool authority and native usage limits.
- Actual owned loopback service histories show separate native model/tool activities, not an opaque agent-loop activity; saved histories replay using the same pinned source/configuration.
- Meaningful invalid citation/tool/limit controls fail in both modes with attributable native errors. No provider requests are allowed in the fixture process.
- Native local spans cover direct and durable model/tool/workflow/activity paths and preserve replay behavior. Missing metrics remain unknown.
- Freeze relevant source, fixtures/oracles, dependency lock and runtime pins before live work. Retain every failed attempt, original process PID/start identity, native histories and confirmed endpoint cleanup under `.runs/four-priorities-20261012/temporal-agent`.
- Native agent composition is qualified only within this fixed scripted fixture envelope. Real reasoning/providers, OpenShell tools, production Temporal, cross-version replay, crash/mid-activity recovery and complete investigation composition remain outside scope.

## Decisions and open questions

Root owns shared dependencies/Make/Git/CURRENT and runtime assignment; no installation or publication by this agent. SDK source/documentation is verified against the selected installed version and retained immutable v2.55.0 documentation, with Context7 used for discovery. Native references: [selected integration docs](https://github.com/pydantic/pydantic-ai/blob/v2.55.0/docs/durable_execution/temporal.md), [selected integration source](https://github.com/pydantic/pydantic-ai/tree/v2.55.0/pydantic_ai_slim/pydantic_ai/durable_exec/temporal). Context7 examples are not standalone compatibility proof.
