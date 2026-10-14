---
id: HANDOFF-0127
kind: handoff
title: Probe validity design reconsideration
status: recorded
updated: 2026-10-13
related: [SPEC-0078, PLAN-0093, ISSUE-0009]
---

# Probe validity design reconsideration

## Verified state

PR130 merged at df5c661242c0a833ab481803e116dc5add016e96. Follow-up branch codex/probe-validity-evidence has local, unpublished commit7300a3676597c91729e72863e284fd845c1ef0fe: per-probe evidence review, component-only planner drafts with runner-owned IDs, evidence navigation and versioned evaluator corrections. Uncommitted authoring skill/prompt/refusal-feedback changes add a short feedback-directed procedure. Preserve unrelated HANDOFF-0118/0119 and the Open-PR re-review CURRENT paragraph outside commits.

User requested independent brainstorming/research before proceeding further. Two Sol6.1 agents reviewed alternatives without changing files or invoking inference. No follow-up PR published, no baseline promoted and no candidate live evaluation started. Existing user authorization for the self-hosted llm.almckay.io/v1 endpoint persists without cost/usage concerns.

## Validation and blockers

Final committed implementation offline selection: 2,163 passed, 6 skipped, 12 warnings in63.42seconds; `.runs/probe-validity-followup/offline/corsair-probe-validity-offline-final.log`. Earlier broad pytest selection, admission errors and replay-fixture correction are retained in the plan/logs. Uncommitted authoring procedural subset:103passed,1warning,4.75seconds in `/tmp/corsair-authoring-procedure-host-tests.log`; initial restricted asyncio run stalled and was interrupted. Source changes after the full offline run are limited to that authoring direction/refusal feedback and work records.

Original before measurements run sequentially from immutable /tmp/corsair-pr130-live at df5c661, driver `/tmp/corsair-run-six-live.py`, exec session87573. Inspect ignored `.runs/pr130-live-merged/active.json`, completed.jsonl and native reports, rather than assuming the process remains alive. At this snapshot: unit planning0/4clean, authoring4/4fixture-portclean, assessment2/7clean; development planning4/12clean, authoring3/20clean; development assessment still running. No generated-test execution qualification follows from injected authoring observations.

Assessment admitted benign input as an exploit; copied/wrong-source targets were incorrectly approved in drafts rejected only by citation contracts. Planning combines native-ID failures with an exact-marker false negative and obsolete witness-only expectations. Authoring includes real forbidden-hook repetition and budget exhaustion, plus evaluator false positives and missing harness assertion facts. Historical promoted datasets/provider caps differ; comparisons require explicit caveats. Campaign semantic qualification stays blocked.

## Decisions and next steps

Keep the existing changes available for comparison, but do not treat their larger review schema as the chosen final design. Proposed experiments: smaller property-focused planning versus implementation-heavy plans; compact source-grounded challenge review versus structured checklist review; one source-only semantic repair followed by fresh review versus reject-only; operator-reviewed safe/unsafe calibration of the same two probes in isolated evaluation. Preserve actual security predicates, source/patch identity, outcome blindness, both native outcomes and strict dependency scope. Do not add an agent ensemble, generic repair framework or mandatory language-specific recorder without demonstrated need.

Research: CoverUp (https://arxiv.org/abs/2403.16218) supports studying targeted contextual feedback for Python coverage, not blanket security correctness. Mathews/Nagappan (https://arxiv.org/abs/2412.14137) reports that pass-oriented test-generation feedback can discard bug-revealing tests. Native PydanticAI retries/tool preparation provide bounded mechanisms; retry count alone is not semantic improvement. These inform hypotheses, not qualification claims.

## Continuation prompt

```text
Read AGENTS.md, CURRENT.md, PLAN-0093, ISSUE-0009 and HANDOFF-0127; verify git and live evidence. Preserve local7300a36, uncommitted authoring guidance and unrelated review notes. User asked to think through alternative architecture before proceeding with changes. Present or follow the settled design/experiment decision before further implementation or publication. Inspect original live baseline progress; preserve its frozen source and all failures. Use existing self-hosted endpoint authorization for approved evaluation work, keep labels/outcomes away from authoring and validity review, execute both native probes, and qualify only measured scope. Update records and a new handoff when work resumes.
```
