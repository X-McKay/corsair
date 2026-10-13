---
id: HANDOFF-0071
kind: handoff
title: Planning agent review handoff
status: recorded
updated: 2026-10-13
related: [SPEC-0047, PLAN-0051, ISSUE-0007, ISSUE-0006]
---

# Planning agent review handoff

## Verified state

Worktree /home/al/.codex/worktrees/agent-planning-review/corsair on codex/agent-planning-improvements, base 6be1b5f55224cbf97dc03a89f8c8a29d79f19df4. Source grounding and identifier-boundary admission implemented; prompt test-planning-v6-grounding-1/config test-planning-config-v3. Resolve the committed revision with Git. No shared runner, dataset, provider or skill changes. PLAN-0051 contains the comprehensive review and limits.

## Validation and blockers

Final command results follow below. Raw receipts and comparisons remain ignored under .runs/evals/planning. The initial new-test construction failure is preserved in PLAN-0051. Scripted native estimates cannot establish provider semantic or efficiency improvement. Live comparison is unrun pending the root-owned provider slot. No infrastructure was created and no untrusted code executed. ISSUE-0007 and ISSUE-0006 continue to limit application admission.

## Decisions and next steps

Root owns publication and optional bounded live comparison; this workstream commits only. Pending PR44 independently adds no-baseline refusal and typed witnesses. Reconcile its prompt/config identities on integration and re-run affected consumer tests. Review actual provider plans before any qualification claim.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, SPEC-0047, PLAN-0051 and this handoff. Inspect Git/source and verify evidence. Use the Corsair development skill. Integrate the planning target-source guard with separately authorized PR44 changes, preserving exactly two native tests and typed witness authority. Run make eval AGENT=planning plus affected tests and make test-config; use an explicit operator provider config for any bounded live comparison. Do not tune on held-out answers or claim runtime qualification from scripted results. Update records and write a new handoff.
```

## Recorded checks

- Baseline make eval AGENT=planning: 12/12 clean development attempts, .runs/evals/planning/20261013T094519Z-development-scripted.
- Final candidate make eval AGENT=planning: 12/12 clean development attempts; .runs/evals/planning/20261013T094905Z-development-scripted (final source, including dollar identifiers). Estimated mean requests 2.5, source tool calls 1.5, input tokens 640.667 and output tokens 193.833, unchanged from baseline. These are scripted estimates.
- Planning native tests: 40 passed before the extra Java/JavaScript dollar-boundary regression; final targeted planner/configuration result: 142 passed, one native event-loop deprecation warning.
- make test-config: 999 passed before new records/dollar-boundary case, one native event-loop deprecation warning. Final records/source rerun: 1000 passed, one native event-loop deprecation warning.
- git diff --check: passed.

## Current-head review correction

Independent review confirmed that Python regex \w excludes valid Unicode identifier continuation marks: a suffixed combining accent was admitted as an exact target. Literal matches now inspect adjacent characters using Python's identifier-continuation check plus Java/JavaScript $. Negative native stage tests cover combining and spacing marks; exact Unicode spellings and existing punctuation/dollar cases remain supported. This lexical rule remains conservative and is not semantic source proof. Prompt/config identity advanced to grounding-2 (planning config v4). No dataset/held-out changes or live provider calls. Earlier broad review-test attempts were interrupted after they stalled in the restricted worktree; subsequent focused checks and scripted comparisons are recorded below.

Focused target/anchor checks:10 passed; development scripted12/12 versus12/12, `.runs/evals/planning/20261013T100740Z-development-scripted`, unchanged estimated requests/tools/tokens.

Final affected planning and documentation/dataset guards:52 passed, one existing event-loop deprecation warning. git diff --check passed. Live candidate rerun and full-suite repeat unrun; prior full-suite source remains separately recorded.

## Conservative cross-language lexical follow-up

Cross-review found Java/JavaScript currency symbols and format characters still accepted as partial-name suffixes. The adjacent-character guard now conservatively includes Unicode Sc and Cf categories together with Python identifier continuations; this covers currency and zero-width joiner/non-joiner suffixes while preserving complete literal spellings. It is intentionally not a parser or declaration/semantic proof. Native negative and complete-spelling checks retain existing dollar and punctuation expectations. Identities advance to grounding-3 (planning config v5). No corpus/held-out, provider or authority changes.

Focused native admission/evaluator checks:21 passed, one existing deprecation warning. Final scripted development12/12 against12/12 at `.runs/evals/planning/20261013T101200Z-development-scripted`, unchanged estimated requests/tools/tokens. The independent implementation_call scorer now applies the defined lexical boundary rather than a substring; mutated-output negatives prove prefix and Unicode suffix sensitivity.
Full-suite repeat, live provider and runtime checks unrun for this bounded correction; earlier checks remain historical. git diff --check passed.
