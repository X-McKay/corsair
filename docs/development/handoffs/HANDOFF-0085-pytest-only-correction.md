---
id: HANDOFF-0085
kind: handoff
title: Pytest-only setup correction
status: recorded
updated: 2026-10-13
related: [SPEC-0053, PLAN-0057, HANDOFF-0084]
---

# Pytest-only setup correction

## Verified state

PR63 branch codex/actionable-blockers started at bf15d9a; merged main 93a0fab. Resolve the commit containing this record through Git. Removed the mvn-to-wrapper correction because admitted images already supply Maven and a wrapper may fetch an unqualified distribution outside runtime admission. Only unrecognized pytest arguments can receive the existing explicit correction allowance (0–2, default two). Preserved PR51's junit4 skill guidance and all budget-refusal/unknown-execution guards. Updated prompt environment-v4-pytest-correction and offered-tool digest 5bdc3e1fff20f9280103e2facc581ae7006ae899810788d97b7a09de22975017.

## Validation and blockers

Full offline `make test-config`: 1326 passed, one existing SDK event-loop deprecation warning. Includes pytest correction, missing-Maven terminal refusal with unchanged/changed wrapper arguments, budget-refused-call readiness and JUnit 4 checks. Frozen `make eval AGENT=environment`: 20261013T122747Z-development-scripted, 16/16 versus previous 16/16; request/tool/command and estimated token means unchanged. Net diff against integrated main passes whitespace checks. No live provider, sandbox or durable qualification. The frozen eight-case set still lacks correction trajectories; existing production FunctionModel tests cover admission rules, not live recovery frequency or side effects.

## Decisions and next steps

Publish to existing draft PR63 and respond to review. Verify exact-head CI; do not merge without user authorization. Future evaluation work can add a separately identified correction dataset without rewriting the frozen baseline. Live effectiveness remains unmeasured. No other component or qualification scope changed.

## Continuation prompt

```text
Read AGENTS.md, CURRENT.md, SPEC-0053, PLAN-0057 and HANDOFF-0085. Verify PR63's actual head and CI. Review the pytest-only correction and main integration, preserving junit4 and the budget-refusal fix. Address concrete review findings, run affected checks and record actual results. Do not infer live qualification from scripted tests or merge without authorization.
```
