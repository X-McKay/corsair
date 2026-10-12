---
id: HANDOFF-0032
kind: handoff
title: Native feature adoption implemented offline
status: recorded
updated: 2026-10-12
related: [PLAN-0022, IDEA-0002, ISSUE-0006, ISSUE-0007]
---

# Native feature adoption implemented offline

## Verified state

Branch `ccr-4c5367ef-tzjpmk`, now merged with main `b61d1e9` (which added the native skill/toolset, numbered source reads, output-function contract, thinking controls, HANDOFF-0030 and HANDOFF-0031). The branch holds the review record IDEA-0002, three work packages (OpenShell adapters, Temporal workflow, PydanticAI agent/provider/evals) re-applied onto main's agent structure, PLAN-0022, and the PR #21 review fixes (per-dimension usage evidence, handoff renumbered to this record). Resolve the published head with `git log -1 origin/ccr-4c5367ef-tzjpmk`. Delivered scope is exactly PLAN-0022's completed steps; nothing is live-qualified, and the live-only review items (gateway metrics, configuration revision polling, prover guard, `request_id` reconciliation, chart value migration, committed replay histories) are not started.

## Validation and blockers

`make test-config` on the head merged with main: 305 passed (baseline 255; 286 before the main merge). Native Temporal tests skip without `--temporal-address` (14 skipped); `tests/qualification` collects but was not run. The fixture evaluation CLI exits 0 with `PYTHONPATH=src:.`. The independent review found no blocking code defect; its contrast check confirmed the new agent, unit and configuration tests fail on the previous source. Unrun: every live OpenShell slice (all now send `SANDBOX_RESTART_POLICY_NEVER` explicitly and pass explicit lifecycle limits at the previous values) and every durable test (renamed workflow/activity types do not replay old histories). ISSUE-0006 and ISSUE-0007 are unchanged.

## Decisions and next steps

Settled in PLAN-0022: explicit `server` selection with `VLLMProvider` and pinned profile overrides; separate tool and output retry budgets; `fixture_id` excluded from prompts; typed workflow request with an operator budget ceiling and typed refusals; honest durable usage accounting; explicit lifecycle limits and restart policy; structured gateway error fields. Next bounded action: re-run the OpenShell adapter and lifecycle slices on a fresh admitted node and the issue-analysis durable composition on an operator-owned Temporal service with this code, then update the qualification reports. PR #21 is open; its first review's three items (main conflicts, partial-usage false zero, duplicate handoff id) are addressed at this head and await re-review.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then PLAN-0022, IDEA-0002 and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. Re-run the OpenShell lifecycle/adapter slices on a fresh admitted node and the issue-analysis durable composition on an operator-owned Temporal service against the merged code, retaining fresh evidence; then update the qualification reports and PLAN-0022. Stop dependent integration if ISSUE-0006 or ISSUE-0007 remains blocked; continue useful independent work such as IDEA-0002 package 1 (policy profiles, lock pin, prover guard). Run make test-config, preserve actual evidence, update work records/CURRENT.md, and write a new handoff.
```
