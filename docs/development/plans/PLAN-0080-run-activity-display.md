---
id: PLAN-0080
kind: plan
title: Run activity in the terminal
status: implemented
updated: 2026-10-13
related: [SPEC-0072, PLAN-0079]
---

# Run activity in the terminal

## Objective and dependencies

Implement [SPEC-0072](../specs/SPEC-0072-run-activity-display.md) on direct mode. Independent of PLAN-0079
(#109): this change touches `composition/direct.py`, which #109 does not, and the fixture CLI's `main()`, which
#109 leaves as is. Once both are merged, `corsair run` opts in with
`with TerminalDisplay(title) as display, observing(display):` around its run.

## Steps

- [x] Events, observer, `observing` and the `Activity` capability in `corsair.composition.progress`.
- [x] `run_chain` and `run_direct` report through `observe`; the durable chain passes none.
- [x] `TerminalDisplay` in `corsair.adapters.terminal`; `rich==15.0.0` pinned (already in the lock).
- [x] Fixture CLI (`evals/fixture_e2e/run.py`) shows the display on stderr.
- [ ] `corsair run` (PLAN-0079) opts in after both PRs merge.

## Validation and progress

- `uv run pytest tests/agents/test_run_activity.py`: 8 passed.
- `make test-config`: 1787 passed (main ed9108b plus this change).
- Scripted fixture CLI (`python -m evals.fixture_e2e.run --evidence <new dir>`, no model calls) printed the
  plain view to a pipe and its JSON summary to stdout unchanged.
- No live model, cluster or durable run.

## Decisions and next action

Native hooks rather than `event_stream_handler`, because the latter streams provider calls. Next: wire
`corsair run` once #109 lands; durable-mode activity is a separate slice.
