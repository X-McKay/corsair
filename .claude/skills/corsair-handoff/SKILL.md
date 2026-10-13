---
name: corsair-handoff
description: Use when ending substantial Corsair work, preparing a new agent session, or writing a continuation prompt. Preserve verified state, work record references, blockers, actual checks, authorization boundaries, and concrete next steps in the repository handoff format.
---

# Corsair handoff

Read `AGENTS.md`, `docs/development/README.md`, `docs/development/CURRENT.md` and the active records. Use `docs/development/templates/handoff.md`.

1. Inspect `git status`, branch and commit identity; distinguish verified facts from assumptions. Do not invent a future commit SHA or claim a dirty workspace is clean.
2. Update the active plan and issue with actual progress, decisions, commands/results, evidence references and outstanding limits. Keep immutable raw evidence outside Git.
3. Create the next `HANDOFF-NNNN-<slug>.md` under `docs/development/handoffs/`. Record the work's base/source revision and how to resolve the current published revision when the handoff is committed with the work. Treat handoffs as snapshots; later sessions add a new one.
4. Include a concise copyable continuation prompt: read root instructions/current work, inspect source/git state, confirm the blocker/current gate, perform the next bounded action, run its relevant checks, and update records. State what would block dependent work.
5. Preserve the accepted unit-test-first direction in investigation continuations: name the real application seam, property and validity evidence; explain any required integration boundary. Missing low-level telemetry alone does not justify a new recorder or a blocked unit test. Link the new handoff and active plan/issues from `CURRENT.md`. Supersede only that pointer; preserve previous handoffs and failure history. Reuse current authorization rather than reopening settled choices.
6. Run the offline record checks if changing process files. Publish repository work only within the user's authorization; do not upload `.runs/`, `.state/`, secrets or raw private logs.

The final user response should stand alone: outcome, meaningful validation, blocker/limitations, next action and useful repository links. A future session must still verify the handoff against source/evidence; it is not a qualification receipt.
