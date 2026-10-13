---
id: HANDOFF-0060
kind: handoff
title: Whole-repository source tools
status: recorded
updated: 2026-10-13
related: [SPEC-0038, PLAN-0042, SPEC-0024, PLAN-0036]
---

# Whole-repository source tools

## Verified state

Branch `claude/repo-scale-source-tools-l7bldu` from main `334aa03`, draft PR. Delivered: `SourceTree` and typed tool results (`src/corsair/agents/source/repository.py`), the bounded native toolset with message-derived byte budget and read-once notice (`repository_tools.py`), identification repository mode with its own input contract, skill and versions (`agents/issue_analysis/repository_identification.py`, skill `identify-issue-repository`), the shared identification finalizer (`identification.py`, behaviour unchanged for the inline mode), offline tests and the measurement/live harness (`evals/repository_identification/`). Only identification uses the tools; planning, authoring, environment and assessment still take the inline inventory. Direct mode only.

## Validation and blockers

- Offline: `tests/agents/test_repository_source.py` 20 passed; existing identification suite unchanged and passing. Full `make test-config` count recorded in PLAN-0042.
- Measurement on JSPWiki f140a2a4 in the container (full bare clone, `GitSource` capture 19.3 s): 1,723 files, 1,471 readable text files; probe of seven tool calls returned 7,944 B of the 131,072 B run budget, and the repeated window returned a 248 B notice. Details in PLAN-0042.
- Live smoke on the local model: unrun at this snapshot.
- Not run: durable mode (unsupported by design for now), other stages, any OpenShell or cluster gate (not needed).

## Decisions and next steps

Settled in SPEC-0038: literal search, Git line semantics, accounting from messages, explicit repository mode with no fallback. Next: live smoke on RIG0; then planning adoption after PR #38 merges (planning's `withdraw_when_read` must be combined with `withdraw_when_spent`, and its `_run_reads` must ignore `RepeatedRead`, as `run_source_reads` does), followed by authoring and assessment with their eval sets rerun.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then SPEC-0038, PLAN-0042 and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. Adopt the SPEC-0038 repository tools in the next read-only stage (test planning once PR #38 is on main) without changing the inline mode's frozen evaluations. Stop if the live identification smoke recorded in PLAN-0042 shows the tools unusable by the local model. Run make test-config and the stage's eval set, preserve actual evidence under .runs/, update the work records and CURRENT.md, and write a new handoff.
```
