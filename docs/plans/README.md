# Current work and plans

This is the current work index. Current user guides start at the [documentation index](../index.md); historical records in [archive](archive/README.md) are evidence, not executable instructions for the current tree.

## This independent recommendation branch

[Stop probes after uncertain cleanup](archive/plans/PLAN-0118-cleanup-fail-closed.md) is implemented on `manus/cleanup-fail-closed`. [Final handoff](archive/handoffs/HANDOFF-recommendation-cleanup-fail-closed.md) and [native receipt](../../evals/baselines/qualifications/qualification-cleanup-fail-closed-2026-10-25.json) record 152 passing physical-Mac tests with zero skips. The base-revision records below retain their original scope and are not the current branch's final qualification.

## Active work


- [ISSUE-0011: expanded producer diagnostics](active/ISSUE-0011-expanded-producer-diagnostics.md) retains the new exact-candidate mismatches; schema validity and passing native tests do not promote them.
- [ISSUE-0010: live safe-case follow-up probe](active/ISSUE-0010-live-safe-case-probe.md) remains open. A later model candidate caused a native execution error after a held/held first round; it must not be relabeled as a successful negative clearance.
- [Next simplifications](active/next-simplifications.md) is a proposal backlog, not implemented behavior or approval to expand scope.

## Final cleanup and authorized publication

[PLAN-0116](archive/plans/PLAN-0116-final-cleanup-and-publication.md) and [HANDOFF-0148](archive/handoffs/HANDOFF-0148-final-cleanup-and-publication.md) record the final cleanup and normal existing-PR push. The latest post-cleanup local full suite passed150 tests in143.52s with0 skips. Producer exact-match diagnostics scored4/9 on this repeat (original case3/3), auditor12/12, with no provider failures. [Local publication receipt](../../evals/baselines/qualifications/qualification-publication-2026-10-25.json) preserves those results and unresolved limits. Exact pushed revision, CI and bundle status are separate delivery receipts, not rewritten earlier history.

## Latest completed consolidation

[PLAN-0115](archive/plans/PLAN-0115-boundaries-and-local-state.md), [PLAN-0114 closure](archive/plans/PLAN-0114-local-storage-retention.md) and [HANDOFF-0147](archive/handoffs/HANDOFF-0147-boundaries-and-local-state.md) record explicit worker composition, canonical environment/private state, maintained documentation/import/privacy gates and careful retained-data cleanup. The full current physical-Mac suite passed150 tests before and after cleanup with0 skips;119 offline tests passed. Old runtime/frozen identities/pins remain intact. The final expanded AI-authored candidate producer scored5/9 and auditor12/12, while the old producer case remained3/3. A separate actual live batch remained2/3: ISSUE-0010 and ISSUE-0011 are still open; no baseline/policy/label was promoted to hide them. Current-revision Linux is unrun. [Qualification receipt](../../evals/baselines/qualifications/qualification-consolidation-2026-10-25.json) separates all cohorts and failed/unrun gates.

## Latest completed eval/test cleanup

[PLAN-0113](archive/plans/PLAN-0113-eval-test-layout.md) and [HANDOFF-0145](archive/handoffs/HANDOFF-0145-eval-test-layout.md) record exact category directories, ordinary helper imports and removal of ignored legacy bytecode. All134 test IDs/order and29 existing eval files are preserved. Final quality/offline checks passed (103 tests,31 deselected); the complete actual Docker/Temporal non-live suite passed133 tests with1 live test intentionally deselected. This is current native composition evidence, not a new model-accuracy or negative-clearance result. The earlier2/3 live-model batch limitation remains open below.

## Latest completed documentation work

[PLAN-0112](archive/plans/PLAN-0112-documentation-layout.md) and [HANDOFF-0144](archive/handoffs/HANDOFF-0144-documentation-layout.md) record the requested documentation hierarchy. All runtime/resource hashes are unchanged. The final locked quality gates and103 offline tests passed after cleanup;31 native/live tests were deliberately deselected, not counted as new qualification. CLI/API/configuration/schema examples and packaged links were checked separately. The root LICENSE records the existing absence of a project-wide license grant; it does not select new terms.

## Current implementation and qualification

The base revision below had canonical Pydantic structured producer output and explicit contracts, ports, adapters, entrypoints, policies, workflows, steps, observability and evaluation packages. The source is a personal-use standard-library Python disclosure-recipe pilot. Remote forge adapters, a standalone HTTP service, general negative clearance and production artifact-host-loss recovery are not implemented claims.

The latest pre-documentation physical-Mac suite passed **134 tests** with real Docker/Temporal and live-auditor checks. The unchanged isolated producer freeze passed **3/3** (one case repeated three times), auditor **6/6** (two cases repeated three times). A separate actual live-model native batch scored **2/3**; ISSUE-0010 retains its operational failure. Current-local-revision Linux amd64 checks have not been rerun. Earlier CI successes refer to their recorded revisions, not a later revision without its exact corresponding checks.

[HANDOFF-0143](archive/handoffs/HANDOFF-0143-structured-output-ports.md) records the implementation and exact evidence; [the sanitized receipt](../../evals/baselines/qualifications/qualification-structured-ports-2026-10-25.json) records its narrow scope. The documentation migration's [handoff](archive/handoffs/HANDOFF-0144-documentation-layout.md) distinguishes its prose-only checks from those runtime results.

## Record conventions

Put a bounded plan in `active/` with its goal, scope, decisions, commands, actual results and blockers. Keep failed and unrun checks. Move completed plans to `archive/plans/`; handoffs to `archive/handoffs/`; resolved issues to `archive/issues/`; historical reviews to `archive/reviews/`. Update this index and relative links in the same change. Work state must distinguish proposed, implemented and qualified behavior.

Do not commit raw `.runs/`, `.state/`, private diagnostics, credentials, model reasoning or unredacted evidence. A sanitized receipt must preserve unknown metrics as unknown and must not turn skipped discovery, denied execution or mocked dependencies into qualification. Publishing, deployment and issue closure remain subject to the user's current authorization.
