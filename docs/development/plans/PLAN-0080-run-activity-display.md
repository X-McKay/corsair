---
id: PLAN-0080
kind: plan
title: Run activity in the terminal
status: in_progress
updated: 2026-10-13
related: [SPEC-0072]
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
- [ ] `corsair run` (PLAN-0079, #109) opts in after both PRs merge.

## Validation and progress

- 6c52477: `uv run pytest tests/agents/test_run_activity.py` 8 passed; `make test-config` 1787 passed on the code
  before these records were added, so it did not cover them (see below).
- Review of 6c52477 (Al, coordinator): masking missed `Authorization: token …`, `NAME=value` inside command
  strings and URL userinfo; chain summaries were built on unwatched runs. Fixed: wider masking with a test per
  form, reporting built only when observed and unable to raise. After merging main: 17 activity tests passed;
  `make test-config` first runs failed the work-record check (status `implemented` is not a valid state;
  `related` named PLAN-0079, which is not on main yet), both fixed; `make test-config` then 1805 passed.
- Codex review of 15b7e21: an `Authorization` value with a short or unknown-scheme credential was only partly
  masked; plain mode printed nothing while a tool ran; concurrent calls to one tool could show each other's
  arguments. Fixed: the whole header value is masked, plain mode prints a start line per tool call, tool events
  carry the call id. 20 activity tests passed; `make test-config` 1808 passed.
- Scripted fixture CLI (`python -m evals.fixture_e2e.run --evidence <new dir>`, no model calls) printed the
  plain view to a pipe and its JSON summary to stdout unchanged.
- No live model, cluster or durable run.

## Decisions and next action

Native hooks rather than `event_stream_handler`, because the latter streams provider calls. Next: wire
`corsair run` once #109 lands; durable-mode activity is a separate slice.
