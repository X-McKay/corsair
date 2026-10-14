---
id: PLAN-0103
kind: plan
title: CLI presentation, JSON and direct lifecycle receipts
status: complete
updated: 2026-10-14
related: [SPEC-0082]
---

# CLI presentation, JSON and direct lifecycle receipts

## Scope and boundaries

PR #175 adds a thin Rich adapter, terminal-only animation, scrolling stderr, NO_COLOR, recorded per-agent telemetry, versioned JSON and honest direct-cancellation receipts. Reject invalid run records without altering probe/disposition, OpenShell or Temporal remote-cancellation semantics. This branch is independent of PRs #174/#176; closed PR #178 is not a dependency and its roadmap is not pursued.

## Review follow-up

Rebased onto inspected develop `a00bbbc96d3b97838398693dea3dcae7c43da6bb`, preserving the chain/recorder changes from #179/#182. Address the owner's 2026-10-14 review:

1. Use one public helper, `runs.printable()`, for table, Rich display and CLI diagnostics. Remove duplicate sanitizers and cross-module private `_safe` imports. JSON retains the unmodified record values.
2. Remove accepted `interrupted` lifecycle state: no recorder writes it. Unknown/unwritten states display as `incomplete`; the reporter may still print an interruption notification, which is not persisted run state.
3. Confirm worker ownership with native Temporal activity-environment and test-server worker regressions, sharing the same presentation callback across two requested run directories. Assert start receipts belong only to each requested path, an unrelated client receipt is untouched and the worker does not create a default `.runs/` directory.
4. Document the `runs compare` exit-code change below and in RUN_RECORD.md.
5. Run focused/full checks, cleanup and re-test, then update the existing draft. Do not merge/deploy automatically.

## Compatibility and recorder ownership

Previously, `runs compare` returned success with `-` columns for a missing run directory. It now returns **exit 2**, writes a diagnostic to stderr and emits **no success output** when any input is missing, empty or malformed. Existing scripts must handle exit 2 or select actual recorded directories before comparison. Valid legacy records still load with missing fields unknown; missing records are no longer presented as successful comparisons.

`LocalOps._report("started")` writes through **its own operation recorder**. Temporal activities construct that recorder from the request's shared `run_dir`, not from a client/default path; the worker's progress callback only presents text. This does not change the shared-filesystem requirement or prove command termination/cleanup. The tests exercise activity and worker paths without real model/container side effects.

## Validation

Original bdbb2a91 standalone checks were 1646 passed/113 skipped in serial and four-worker runs, focused/post-cleanup 29 passed, and scripted chain 100/100. Those are retained history, not current review validation.

Review follow-up validation completed on the pinned a00bbbc base; commands/results below.

Unrun: Docker/kind/OpenShell gateway, production provider/native disposition benchmarks and remote cleanup/durability failure qualification. Native test-server routing with deterministic stage/model doubles is not production workspace or accuracy evidence. No baselines/prompts are promoted; raw `.runs/`, `.state/`, credentials and diagnostics stay out of Git.

## Completed owner-review validation

Base: `a00bbbc96d3b97838398693dea3dcae7c43da6bb`.

| Check | Result |
| --- | --- |
| Focused boundary/configuration tests | 138 passed |
| Four-worker make test-v2 | 1718 passed, 113 skipped |
| Serial make test-v2 | 1718 passed, 113 skipped |
| Diff cleanup and focused re-test | diff check passed; 138 passed |

Whole-chain scripted evaluator passed; no baseline promoted.

All owner review items are addressed in this branch. The current PR/plan/index provide the next-session context: inspect source/CI, review the bounded diff and keep live qualification separate. PR #178 remains closed and no audit/roadmap continuation is part of this follow-up. Do not merge or promote automatically.
