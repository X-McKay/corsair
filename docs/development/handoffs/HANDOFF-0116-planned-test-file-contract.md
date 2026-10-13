---
id: HANDOFF-0116
kind: handoff
title: Planned test ids must name a test in their approved file
status: recorded
updated: 2026-10-13
related: [PLAN-0089, PLAN-0087, SPEC-0022, HANDOFF-0113]
---

# Planned test ids must name a test in their approved file

## Verified state

Branch `claude/approved-paths-contract-sb61zp` from main `1815f75`; resolve the commit carrying this document from Git. PLAN-0087 lane 2 is implemented offline under [PLAN-0089](../plans/PLAN-0089-planned-test-file-contract.md). The directory form of the mismatch was fixed on main by PR #120 and is refused there. The remaining mechanism was planning admitting a test id that names a different file than its approved `test_path`, which authoring then refused after planning had finished. One rule in the test-runner port (`names_test_in`) now governs both planning admission and the authoring handoff for all five runner grammars. Prompts, skills, schemas and frozen eval sets are unchanged.

## Validation and blockers

The new planning test failed on main for five layouts and passes now. Scripted `make eval` for planning, authoring, environment and chain was identical before and after apart from timing; planning `heldout3` was 12/12 scripted. The offline suite passed 1971 tests. No live model or Docker run was possible from this cloud container (no access to the provider or RIG0 Docker). Live behaviour is unqualified.

## Decisions and next steps

Keep planning output exhaustion as its own hypothesis. The authoring handoff still admits only pytest and Minitest ids (Jest has a reader but is refused; TAP and JUnit have none); that is for the non-Python path lane. Next bounded action: the campaign owner runs the live planning development set at this commit against the promoted baseline, then the diagnosed `ih-python-pathtraversal` successor on Docker, recording whether the model was shared.

## Continuation prompt

```text
Read AGENTS.md, docs/development/CURRENT.md, PLAN-0087, PLAN-0089 and this handoff. Verify the branch or merged commit carrying names_test_in in src/corsair/ports/test_runner.py. As the single live-inference user, run `make eval AGENT=planning PROVIDER_CONFIG=<operator file>` at that commit and compare with the promoted planning baseline; then run the next ih-python-pathtraversal attempt through `corsair run` on Docker. Record stage, stop reason and whether planning stopped on output exhaustion (separate hypothesis) or on the id/path rule. Update PLAN-0089, CURRENT.md and write a new handoff.
```

## Addendum: empty build step and live results

Slice two of PLAN-0089 (`a7c059f`, PR #129) lets the environment's `build_command` be empty when a project has nothing to build. The live planning comparison for slice one was 10/12 vs 11/12, and its failures fall before the new rule. The pathtraversal successor was INCONCLUSIVE because the authored test imported a copy of the target. The live environment eval was 0/16 on both sides, because it scores exact argv. `ih-python-healthcheck-3` passed environment without correction and stopped correctly at planning on a missing database-call witness. Next actions belong to the campaign owner: authored tests that run a copy of the target, reasoning-only output after the single correction, and the database-call witness gap. PLAN-0089 is complete.
