---
id: SPEC-0072
kind: spec
title: Run activity in the terminal
status: draft
updated: 2026-10-13
related: [SPEC-0043, SPEC-0068, PLAN-0079, PLAN-0080]
---

# Run activity in the terminal

## Goal and scope

When a run goes through a command line, the user sees where it is and what it is doing: the current stage
and agent, each model turn, each tool call with its outcome, every retry and model error, and what each stage
has spent against its caps (tool calls, tokens, seconds). On a terminal this is colored and cleanly formatted;
off a terminal it is plain lines. The evidence files stay the record; the display is a view and never feeds
results, routing or evals.

Out of scope: durable mode (stages run in Temporal workers; their activity does not reach the client process),
and persisting the events.

## Boundaries and design

- `corsair.composition.progress` holds the typed events (stage started/ended, model turn, tool called/returned,
  retry, model failed, revision started/ended, gate decided, run ended) and the observer type, a plain callable.
- `run_chain` takes `observe` (default: ignore) and reports stage boundaries, revision runs and the gate. It
  never changes routing. `run_direct` takes `observe`, defaulting to the one `progress.observing()` set in the
  current context, so an entry point opts in once around its run without threading an argument through.
- Inside agent stages, PydanticAI's native capability hooks report activity: a per-run `Activity` capability
  (`after_model_request`, `on_model_request_error`, `wrap_tool_execute`, `on_tool_validate_error`,
  `on_output_validate_error`). It hands every value on unchanged and re-raises every error. It is attached only
  when someone observes, so unobserved runs, evals and baselines keep their exact code path. No streaming is
  switched on (`event_stream_handler` would change the provider call to a streamed one).
- Text is cleaned once, when the event is made: control characters and escape sequences are removed (repository
  and model text cannot drive the terminal), credential-shaped values and arguments under secret-like names are
  masked, and long text is cut. Provider configuration is never an event.
- `corsair.adapters.terminal.TerminalDisplay` (rich 15.0.0, pinned) is the view. On a terminal it shows a
  colored log under a live status line (stage, turn, budget spent, running tool). Elsewhere (a pipe, a log
  file, `TERM=dumb`) it prints plain UTC-timestamped lines with no colors, cursor movement or wrapping;
  `NO_COLOR` removes colors. It writes to stderr, so a command's stdout (a result line or JSON) stays
  machine-readable.

## Acceptance and validation

Offline (`tests/agents/test_run_activity.py`): a complete scripted chain reports every stage, both revisions and
the gate in order, with per-stage spend equal to each attempt's receipt; a stopped run reports its stage and
reason and nothing after; `observing` reaches only runs inside it; the hooks report turns, tool outcomes
(ok, retry, error), argument and output retries and model errors while the run's output and message history
are unchanged; hostile text loses its control sequences and credentials; the plain and terminal views render the
same events.

## Decisions and open questions

- Al asked (2026-10-13 17:36Z) for the run's state and activity to be visible in the terminal with clean
  formatting and colors.
- Durable mode: a later slice could report stage boundaries from the workflow through a query or a client-side
  history poll; not built here.
