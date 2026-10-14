---
name: corsair-handoff
description: Use when ending substantial Corsair work or preparing a continuation. Preserve verified revision, delivered scope, actual tests and limitations, current records and a copyable next bounded action.
---

# Corsair handoff

Read `AGENTS.md`, `docs/development/README.md`, `docs/development/CURRENT.md` and active records. Use `docs/development/templates/handoff.md`. Reference SPEC-0082 rather than repeating its agent, protocol or policy rules.

1. Inspect branch, commit and working tree. Separate source-verified facts, test observations and unknown qualification. Do not invent a future commit hash or call a dirty checkout clean.
2. Update the living plan/issue with actual scope, decisions, commands, failed attempts and blockers. Keep raw private evidence in ignored `.runs/` or an uncommitted evidence root.
3. Create the next unused `HANDOFF-NNNN-<slug>.md`; check main and develop numbering. Preserve prior handoffs as snapshots. State the base revision and how the user can resolve the delivered revision with Git.
4. Include a copyable continuation: read root/current instructions, inspect source/Git, verify the active gate, perform the next bounded action, run proportionate tests and update records. Name what blocks dependent integration; continue useful independent work when possible.
5. Link the handoff and active record from `docs/development/CURRENT.md`. Preserve current user authorization rather than reopening settled routine choices. State live provider/workspace/Temporal/OpenShell checks as unrun unless actual receipts prove them.
6. Run `make test-config` for changed process files. For implemented code, report focused tests, final cleanup and the post-cleanup re-test. Publish/package only authorized source and sanitized documentation, never `.runs/`, secrets or private transcripts.

Make the final response stand alone: outcome, meaningful validation, limitations, next action and direct links to intended deliverables. A handoff is context, not a qualification receipt.
