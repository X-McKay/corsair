---
id: HANDOFF-0036
kind: handoff
title: PR22 review response and skill-protocol checkpoint
status: recorded
updated: 2026-10-12
related: [HANDOFF-0035, HANDOFF-0034, IDEA-0003, SPEC-0022, SPEC-0023, PLAN-0023, PLAN-0018, ISSUE-0007]
---

# PR22 review response and skill-protocol checkpoint

## Verified state

Branch `agent-graph-gap-review`, cut from main `afb75f3` and merged with current main `0578521` (native canary, immutable JSPWiki capture and reviewed draft from HANDOFF-0034; PR22 review checkpoint from HANDOFF-0035). Two record conflicts were resolved by keeping both sides: the new work row above main's updated native-feature row in CURRENT.md, and both appended notes in PLAN-0018. Resolve the published head of this response from Git; the PR is [#22](https://github.com/X-McKay/corsair/pull/22).

Delivered on this branch: IDEA-0003 (remaining agent inventory and read-only-first order), SPEC-0022 and SPEC-0023 as drafts, PLAN-0023 with its first two steps, `evals/issue_analysis/rubric.py` with the failure taxonomy, per-case `CaseRubric`, per-attempt `AttemptLabel`, the native `cases.yaml` dataset and the seed `attempt_labels.yaml`, and `tests/agents/test_issue_analysis_rubric.py`. No agent, provider, workflow, policy, pin or budget changed. Both specs authorize nothing; ISSUE-0007 remains blocked.

The four PR22 review items are addressed at this head: calibration labels now identify individual outputs and keep provider failures separate (`AttemptLabel`, with the case-level union renamed to `reported_failure_history`); SPEC-0022's output is a status discriminated union so `unsupported` needs no fabricated test pair, with a negative fixture named; SPEC-0023 and PLAN-0023 separate an exploratory threshold-selection run from a confirmation run on a disjoint labeled set with false approvals reported separately; this handoff is the required one, numbered after main's HANDOFF-0035.

## Validation and blockers

Offline only: `tests/agents/test_issue_analysis_rubric.py` 6 passed; `make test-config` 369 passed in 11.23s with the existing event-loop warning. No inference, Temporal, OpenShell or downloaded-project execution ran. GitHub reported zero check runs on the previous head; CI on this head must be read from the PR.

Blocked: private retained outputs and the endpoint are absent from the container that produced this work, so no attempt label has an output SHA256 and no judge run, baseline or candidate comparison exists. Zero entries are calibration-ready. The four coded cases are all Python path traversal.

## Decisions and next steps

Calibration truth is per identified attempt, never a case history; threshold selection and confirmation use disjoint label sets; the planner's abstention is a typed branch, not a degenerate ready plan. Existing authorization covers tracked commits and pushes to this branch and PR comments; merging PR22 is the owner's call. Next bounded action: code the private review findings into identified `AttemptLabel` entries where the retained copies exist, then the held-out and skill hygiene guards. Dependent integration (judge scoring, candidate promotion) stays stopped until a confirmation run meets the frozen numbers.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then PLAN-0023, SPEC-0023, SPEC-0022, ISSUE-0007 and this handoff. Inspect git state and PR #22's current head and comments. Use the Corsair development skill. If the private retained ISSUE-0007 outputs are available, code their independent review findings as identified AttemptLabel entries with output SHA256 and split them into disjoint exploratory and confirmation sets; otherwise add the held-out manifest guard and the SKILL.md hygiene guard. Do not run a judge or score any skill candidate before a confirmation run meets frozen numbers. Run make test-config, update PLAN-0023 and CURRENT.md, and write a new handoff.
```
