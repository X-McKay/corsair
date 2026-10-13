---
id: HANDOFF-0125
kind: handoff
title: Unit-test agent skill and tool audit
status: recorded
updated: 2026-10-13
related: [SPEC-0078, PLAN-0093]
---

# Unit-test agent skill and tool audit

## Verified state

Reviewed planning, authoring and assessment skills, prompts, tool registration and relevant admission/finalization paths at f2477f486b39d6f03096d08f3d3946073ef04db1. Branch codex/unit-test-first-validation, PR #130. The user requested review and improvements to skills/tools related to the unit-test change. Existing publication authorization applies; no merge or deployment. Preserve unrelated HANDOFF-0118/0119 and their local CURRENT paragraph.

Fixed two assessment guidance inconsistencies: final disposition had been told to cite source items unavailable in that phase, and legacy witness disposition was described as having a prior unit-validity review. Prompt and skill now distinguish pre-execution validity, unit disposition consuming the frozen test-validity item, and legacy witness disposition. They direct reads/citations only to the current inventory. Added explicit use of typed environment.assertion_facts in planning/authoring skills. Bumped the three prompt versions.

No new tools, agents or runtime-specific policy branches are needed. The evidence tool reads only admitted items; test writing and finalization use the same witness_required mode for dependency-double policy. Existing tools retain bounded reads, approved writes and development run restrictions. Skills preserve both executed probes, real source calls, relevant assertions and dependency boundaries across languages/frameworks/CWEs.

## Validation and blockers

Affected agent/composition/manifest tests: **253 passed, 4 inherited warnings in 6.83s**, `.runs/pr130-skill-audit/tests.log`. Skill metadata checks pass for all three agent skills; git diff check is clean. Frozen scripted legacy planning12/12, authoring20/20 and assessment54/54 remain clean; unit sets planning2/2, authoring2/2 and assessment7/7 (repeat1), no task/evaluator failures. Reports are under `.runs/evals/<agent>/20261013T2332*-{development,unit}-scripted/`, wrapper logs under `.runs/pr130-skill-audit/`. These compare with the preceding same-set scripted runs; no live baseline is promoted.

CI on f2477f4 completed successfully. Full offline suite2108passed/6skipped and additional durable converter check belong to that preceding implementation; this skill-only follow-up uses affected checks rather than claiming a repeated full suite. Live semantic evaluation remains blocked pending destination approval as recorded in HANDOFF-0124; no live call was attempted here. Historical Temporal replay and broader runtime/source-size qualification remain unrun.

## Decisions and next steps

Keep phase-specific evidence instructions aligned with the actual input/tool inventory. Runtime framework facts belong in typed harness data, not shared skill recipes. Continue live semantic qualification only with approved provider destination; scripted success does not prove a model follows the skills. Preserve the unit-test default and do not add recorders to compensate for an unmeasured semantic-review gap.

## Continuation prompt

```text
Read AGENTS.md, CURRENT.md, SPEC-0078, PLAN-0093 and HANDOFF-0125. Verify PR #130 and source/evidence state. Preserve unrelated review records. Keep both probes required and validity review outcome-blind and immutable during disposition. Use current phase inventories for reads/citations, and framework assertion facts from typed environment data. Continue proportionate evaluation; live provider calls await destination approval. Record actual results and avoid broad runtime or semantic-quality claims from scripted checks.
```
