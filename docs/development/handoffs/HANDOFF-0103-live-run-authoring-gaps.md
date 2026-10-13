---
id: HANDOFF-0103
kind: handoff
title: Live-run gaps in authoring, the fixture CLI and the runbooks
status: recorded
updated: 2026-10-13
related: [PLAN-0035]
---

# Live-run gaps in authoring, the fixture CLI and the runbooks

## Verified state

Branch `claude/toolchain-ruby31-6f6z4l` from main `ed9108b`, PR #111. These are three gaps found by the first live fixture end-to-end run (live-002, evidence held by the "Live end-to-end fixture run" thread on RIG0).

- **Withdrawn-tool call:** the live author called `write_test_file` after the reviewed workspace refused its tests. The tool had been withdrawn, so PydanticAI refused it as unknown, and with tool retries at 0 the stage failed with `UnexpectedModelBehavior`.
  - Authoring now carries `Hooks(node_run_error=end_on_withdrawn_call)` (`agents/test_authoring/validation.py`). It recovers the failed tool-call node with a trusted `BlockedAuthoring` that keeps the files and runs so far.
  - The reason reads `the author called <tool> after it was withdrawn: <why>`, where the why comes from `tools/_preparation.withdrawal` (workspace failure with its errors, run budget spent, or admission refusals spent). The `prepare` hook uses the same function.
  - The layer is `admission` when the refusals are spent and `unknown` otherwise.
  - The config is now `test-authoring-config-v4` (supersedes v3 wherever CURRENT or older handoffs name it). The prompt stays `test-authoring-v8`.
- **Relative evidence path:** `evals/fixture_e2e/run.py` makes `--evidence` absolute after its existence check, because `LocalArtifacts` needs an absolute root and the README uses a relative path.
- **Runbooks:** `openshell-adapter-execution`, `openshell-adapter-lifecycle` and `openshell-recovery` now run `make toolchain-images` before `make toolchain-images-load`, as `openshell-toolchains` already did. The fixture README points to that runbook.

## Validation and blockers

- `make test-config`: 1780 passed.
- `make eval AGENT=authoring` (scripted): 18/18 clean, compared with the previous scripted run.
- The authoring tests cover a rewrite after a workspace failure and a run after the run budget is spent. Both now end blocked with the trusted reason; the first previously expected `UnexpectedModelBehavior`.
- A scripted fixture CLI run with a relative `--evidence` path completed.
- No live model call was made. The live authoring baseline is unchanged and still owed for the v8 prompt and the v4 config.

## Decisions and next steps

- The recovery lives in the authoring agent rather than the shared composition runner. That way direct and durable modes both get it, and the other stages keep their classification.
- No new result layer was added.
- Next: when the live fixture run is repeated, confirm that a withdrawn call now ends as `blocked`.

## Continuation prompt

1. Read AGENTS.md, CURRENT.md, PLAN-0035's latest note and this handoff.
2. Check `end_on_withdrawn_call` and `withdrawal` against source.
3. On the next live fixture or chain run, inspect the authoring attempt receipt for a `blocked` result whose reason names a withdrawn tool.
4. Record live results in PLAN-0035 without rewriting earlier failures.
