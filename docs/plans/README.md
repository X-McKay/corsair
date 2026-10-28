# Current work and plans

This is the current work index. Current user guides start at the [documentation index](../index.md); historical records in [archive](archive/README.md) are evidence, not executable instructions for the current tree.

## Proposed intake agent

[PLAN-0130](active/PLAN-0130-intake-agent-design.md) specifies the approved structured intake role for issue references or JSON, sandboxed repository inspection, recommendations restricted to available images, trusted capability admission, and deterministic frozen evaluation. [PLAN-0131](active/PLAN-0131-intake-implementation.md) tracks implementation and actual qualification gates; model accuracy is not promoted. [PLAN-0132](active/PLAN-0132-recipe-free-investigations.md) specifies the user-requested expansion to sandboxed agent-authored test plans throughout investigations, approved by the user on 2026-10-27. [PLAN-0133](active/PLAN-0133-recipe-free-implementation.md) tracks inline implementation and its separate qualification gates.

## Intake quality follow-up

[PLAN-0134](active/PLAN-0134-intake-quality.md) tracks the bounded intake improvement: complete-read grounding, content-free schema diagnostics, native JSON completion and clearer issue/capability categories. The final unchanged cohort scored **14/16 exact and 16/16 correct decisions** across two repeats (6/8 and 8/8 exact), versus **0/8 exact and 3/8 correct decisions** in the fresh control. No final invalid outputs or false-supported cases occurred. These authored candidate diagnostics remain separate from held-out or promoted baselines; v3 producer/full-chain failures remain open.

[PLAN-0135](active/PLAN-0135-intake-json-robustness.md) adds a separate scanner/JSON robustness cohort, normalization-detail assertions and hard JSON admission boundaries. The original eight cases remain frozen; scanner-shaped candidates and repeated related reports are not held-out families.

[PLAN-0136](active/PLAN-0136-intake-image-tool.md) adds the user-requested image-selection tool and native procedural skill. [PLAN-0137](active/PLAN-0137-intake-investigation-handoff.md) records the implemented intake-gated workflow and immutable image/source handoff, with separate native and live stopping results. Model accuracy and full live execution remain unqualified; see [the diagnostic](../../evals/experiments/2026-10-28-intake-pipeline.md).

## Recipe-free v3 implementation

The new default investigation path uses canonical test plans, categorical outcome-blind audit and generic sandbox execution. The reviewed changes preserve unresolved security assessment and versioned historical diagnostics. Latest recorded native gates include **317 offline tests** and **11 Docker/Temporal/replay checks**; qualification details and retained failures are in [PLAN-0133](active/PLAN-0133-recipe-free-implementation.md). The approved continuation scored **1/8 exact intake cases** (2/8 classification), **3/4 exact independent role cases**, and an **INCOMPLETE** full-chain attempt caused by invalid producer output before audit/execution. Earlier **2/4** role reports remain retained. [ISSUE-0015](active/ISSUE-0015-intake-v3-live-quality.md) records the open qualification gap; model reliability remains unqualified.

## Current scoped outcomes and language recipes

[PLAN-0127](archive/plans/PLAN-0127-outcomes-node-java.md) and [HANDOFF-0150](archive/handoffs/HANDOFF-0150-outcomes-node-java.md) record local implementation of versioned paired outcomes and concrete Node ESM/Java static-String recipes. The final physical-Mac suite passed **285 tests, zero skips**, including actual Docker, Temporal/replay, CLI/rescore, installed-wheel and live-auditor checks. [Sanitized qualification](../../evals/baselines/qualifications/qualification-outcomes-node-java-2026-10-25.json) separates native, isolated-role and full-live cohorts.

Model reliability remains unpromoted: the final live candidate batch resolved **1/4** assessments (`DEMONSTRATED`), with three incomplete and one operational failure. [ISSUE-0014](active/ISSUE-0014-node-java-assessment-live-quality.md) retains audit, control/probe and finite-protocol quality gaps. `NOT_DEMONSTRATED` is never a fallback for missing execution, rejected audit or abstention. Current-revision Linux/CI is unrun; this evolution remains local and uncommitted/unpushed pending publication authorization.

## Probe attribution and auditor-consistency follow-up

[PLAN-0128](archive/plans/PLAN-0128-probe-auditor-consistency.md) and the [sanitized experiment](../../evals/experiments/2026-10-26-probe-auditor-consistency.md) record the next, distinct resource identity. The Java error was a malformed model-proposed relative path, not an observer defect. A native regression preserves the wrong path as `ERROR` and validates the corrected path. Revised auditor diagnostics matched **20/20** unchanged Node/Java decisions (baseline **15/20**, including one provider failure), while preserved Python safety remained **12/12**.

One new real ADK/Docker/Temporal batch completed **4/4** assessments: two `DEMONSTRATED`, two `NOT_DEMONSTRATED` after the unchanged two-round guarded-case protocol. The final physical-Mac suite passed **289 tests, zero skips**. These results do not close [ISSUE-0014](active/ISSUE-0014-node-java-assessment-live-quality.md): final producer exact matching was only **5/20**, including two provider failures, and java01 reached the declared fixture in only **2/5** proposals. Earlier failures remain preserved; repeated reliability, human-reviewed held-out cohorts and current-working-tree Linux/CI remain outstanding. Nothing in this follow-up was committed or pushed.

## Producer skills and pure mechanical helpers

[PLAN-0129](archive/plans/PLAN-0129-producer-skills-and-tools.md) and its [sanitized experiment](../../evals/experiments/2026-10-26-producer-skills-and-tools.md) record implemented native ADK `preview_invocation` and `relative_path` helpers plus revised source-grounding guidance. The final physical-Mac suite passed **321 tests, zero skips**. All frozen inputs and auditor resources remain unchanged; canonical contracts, trusted evidence and the finite protocol were not relaxed.

The helper-surface diagnostic produced **16/20 valid native pairs** and 12/20 exact matches, versus 8/20 valid pairs and 4/20 exact matches with the same revised skill alone. However, neither arm called a tool, median helper-surface episode latency was slower, and the distinct full live batch resolved only **2/4** (both Java cases; Node cases remained incomplete). [ISSUE-0014](active/ISSUE-0014-node-java-assessment-live-quality.md) stays open: no causal tool benefit, speedup, majority reliability or Python non-regression is promoted. Earlier failures/results and the stale-assertion first native sweep remain retained. Current-tree Linux/CI remains unrun; no changes were committed or pushed.

## Previous consolidated role-local implementation

[PLAN-0126](archive/plans/PLAN-0126-agent-layout-and-runtime-skills.md) and [HANDOFF-0149](archive/handoffs/HANDOFF-0149-agent-runtime-layout-and-consolidation.md) record the role-local layout, native mandatory procedure preload, optional role-filtered loaders and transparent usage provenance. Real physical-Mac native gates passed209 tests before and after final cleanup; the fresh wheel loaded role skills and canonical identity views outside the checkout. [Qualification receipt](../../evals/baselines/qualifications/qualification-agent-runtime-layout-2026-10-25.json) separates all cohorts and retained failures.

[PLAN-0125](archive/plans/PLAN-0125-consolidate-recommendations.md) preserves the preceding all-eight-head consolidation stage. The latest schema/port/safety corrections and public developer skills are included on manus/just, not main. Final runtime-source/fixture identities, packaging and normal-push CI are tracked in the handoff; earlier per-PR CI is not a current-tip gate.

Required guidance reached all30 new isolated attempts, but the unchanged original producer scored2/3, original auditor2/6, expanded producer3/9 and expanded auditor6/12. The fresh full-live batch scored2/3 with one component CONDITIONAL resolution and two INCONCLUSIVE rows, zero operational failures and no forbidden labels. [ISSUE-0013](active/ISSUE-0013-runtime-procedure-live-quality.md) explicitly retains the new prompt/resource quality limits. [ISSUE-0012](active/ISSUE-0012-producer-decision-live-quality.md) remains open; context presence/native conformance never promote model accuracy or fabricate tool calls.

## Included recommendation records

[Require pinned evidence image identity](archive/plans/PLAN-0117-image-identity.md) is implemented on `manus/image-identity`. [Final handoff](archive/handoffs/HANDOFF-recommendation-image-identity.md) and [native receipt](../../evals/baselines/qualifications/qualification-image-identity-2026-10-25.json) record 155 passing physical-Mac tests with zero skips. The base-revision records below retain their original scope and are independent-stage records, not the consolidated configuration's qualification.

[Stop probes after uncertain cleanup](archive/plans/PLAN-0118-cleanup-fail-closed.md) is implemented on `manus/cleanup-fail-closed`. [Final handoff](archive/handoffs/HANDOFF-recommendation-cleanup-fail-closed.md) and [native receipt](../../evals/baselines/qualifications/qualification-cleanup-fail-closed-2026-10-25.json) record 152 passing physical-Mac tests with zero skips. The base-revision records below retain their original scope and are independent-stage records, not the consolidated configuration's qualification.

[Add typed terminal producer abstention](archive/plans/PLAN-0119-producer-abstention.md) is implemented on `manus/producer-abstention`. [Final handoff](archive/handoffs/HANDOFF-recommendation-producer-abstention.md) and [native receipt](../../evals/baselines/qualifications/qualification-producer-abstention-2026-10-25.json) record 153 passing physical-Mac tests with zero skips. The feature is draft/unpromoted; [ISSUE-0012](active/ISSUE-0012-producer-decision-live-quality.md) retains the failed live gates. The base-revision records below retain their original scope and are independent-stage records, not the consolidated configuration's qualification.

[Bound terminal result payloads](archive/plans/PLAN-0120-terminal-payload-bounds.md) is implemented on `manus/terminal-payload-bounds`. [Final handoff](archive/handoffs/HANDOFF-recommendation-terminal-payload-bounds.md) and [native receipt](../../evals/baselines/qualifications/qualification-terminal-payload-bounds-2026-10-25.json) record 160 passing physical-Mac tests with zero skips. The base-revision records below retain their original scope and are independent-stage records, not the consolidated configuration's qualification.

[Validate evaluation CLI bounds before I/O](archive/plans/PLAN-0121-eval-cli-bounds.md) is implemented on `manus/eval-cli-bounds`. [Final handoff](archive/handoffs/HANDOFF-recommendation-eval-cli-bounds.md) and [native receipt](../../evals/baselines/qualifications/qualification-eval-cli-bounds-2026-10-25.json) record 162 passing physical-Mac tests with zero skips. The base-revision records below retain their original scope and are independent-stage records, not the consolidated configuration's qualification.

[Write complete dataset-bound reports once](archive/plans/PLAN-0122-eval-report-provenance.md) is implemented on `manus/eval-report-provenance`. [Final handoff](archive/handoffs/HANDOFF-recommendation-eval-report-provenance.md) and [native receipt](../../evals/baselines/qualifications/qualification-eval-report-provenance-2026-10-25.json) record 153 passing physical-Mac tests with zero skips. The base-revision records below retain their original scope and are independent-stage records, not the consolidated configuration's qualification.

[Classify exact-match diagnostic failures](archive/plans/PLAN-0123-eval-match-diagnostics.md) is implemented on `manus/eval-match-diagnostics`. [Final handoff](archive/handoffs/HANDOFF-recommendation-eval-match-diagnostics.md) and [native receipt](../../evals/baselines/qualifications/qualification-eval-match-diagnostics-2026-10-25.json) record 156 passing physical-Mac tests with zero skips. The base-revision records below retain their original scope and are independent-stage records, not the consolidated configuration's qualification.

[Use one effective sandbox probe deadline](archive/plans/PLAN-0124-probe-deadline.md) is implemented on `manus/probe-deadline`. [Final handoff](archive/handoffs/HANDOFF-recommendation-probe-deadline.md) and [native receipt](../../evals/baselines/qualifications/qualification-probe-deadline-2026-10-25.json) record 152 passing physical-Mac tests with zero skips. The base-revision records below retain their original scope and are independent-stage records, not the consolidated configuration's qualification.

## Active work

- [ISSUE-0012: producer-decision live quality](active/ISSUE-0012-producer-decision-live-quality.md) is unpromoted despite native/schema coverage.

- [ISSUE-0011: expanded producer diagnostics](active/ISSUE-0011-expanded-producer-diagnostics.md) retains the new exact-candidate mismatches; schema validity and passing native tests do not promote them.
- [ISSUE-0010: live safe-case follow-up probe](active/ISSUE-0010-live-safe-case-probe.md) remains open. A later model candidate caused a native execution error after a held/held first round; it must not be relabeled as a successful negative clearance.
- [Historical simplification review](archive/reviews/2026-10-25-next-simplifications-base-review.md) preserves its original base-review context; several items are now shipped, and it is not current implementation guidance.

## Earlier cleanup and publication stage

[PLAN-0116](archive/plans/PLAN-0116-final-cleanup-and-publication.md) and [HANDOFF-0148](archive/handoffs/HANDOFF-0148-final-cleanup-and-publication.md) record the final cleanup and normal existing-PR push. The latest post-cleanup local full suite passed150 tests in143.52s with0 skips. Producer exact-match diagnostics scored4/9 on this repeat (original case3/3), auditor12/12, with no provider failures. [Local publication receipt](../../evals/baselines/qualifications/qualification-publication-2026-10-25.json) preserves those results and unresolved limits. Exact pushed revision, CI and bundle status are separate delivery receipts, not rewritten earlier history.

## Earlier local-state consolidation

[PLAN-0115](archive/plans/PLAN-0115-boundaries-and-local-state.md), [PLAN-0114 closure](archive/plans/PLAN-0114-local-storage-retention.md) and [HANDOFF-0147](archive/handoffs/HANDOFF-0147-boundaries-and-local-state.md) record explicit worker composition, canonical environment/private state, maintained documentation/import/privacy gates and careful retained-data cleanup. The full current physical-Mac suite passed150 tests before and after cleanup with0 skips;119 offline tests passed. Old runtime/frozen identities/pins remain intact. The final expanded AI-authored candidate producer scored5/9 and auditor12/12, while the old producer case remained3/3. A separate actual live batch remained2/3: ISSUE-0010 and ISSUE-0011 are still open; no baseline/policy/label was promoted to hide them. Current-revision Linux is unrun. [Qualification receipt](../../evals/baselines/qualifications/qualification-consolidation-2026-10-25.json) separates all cohorts and failed/unrun gates.

## Latest completed eval/test cleanup

[PLAN-0113](archive/plans/PLAN-0113-eval-test-layout.md) and [HANDOFF-0145](archive/handoffs/HANDOFF-0145-eval-test-layout.md) record exact category directories, ordinary helper imports and removal of ignored legacy bytecode. All134 test IDs/order and29 existing eval files are preserved. Final quality/offline checks passed (103 tests,31 deselected); the complete actual Docker/Temporal non-live suite passed133 tests with1 live test intentionally deselected. This is current native composition evidence, not a new model-accuracy or negative-clearance result. The earlier2/3 live-model batch limitation remains open below.

## Latest completed documentation work

[PLAN-0112](archive/plans/PLAN-0112-documentation-layout.md) and [HANDOFF-0144](archive/handoffs/HANDOFF-0144-documentation-layout.md) record the requested documentation hierarchy. All runtime/resource hashes are unchanged. The final locked quality gates and103 offline tests passed after cleanup;31 native/live tests were deliberately deselected, not counted as new qualification. CLI/API/configuration/schema examples and packaged links were checked separately. The root LICENSE records the existing absence of a project-wide license grant; it does not select new terms.

## Earlier implementation-stage qualification

The base revision below had canonical Pydantic structured producer output and explicit contracts, ports, adapters, entrypoints, policies, workflows, steps, observability and evaluation packages. The source is a personal-use standard-library Python disclosure-recipe pilot. Remote forge adapters, a standalone HTTP service, general negative clearance and production artifact-host-loss recovery are not implemented claims.

The latest pre-documentation physical-Mac suite passed **134 tests** with real Docker/Temporal and live-auditor checks. The unchanged isolated producer freeze passed **3/3** (one case repeated three times), auditor **6/6** (two cases repeated three times). A separate actual live-model native batch scored **2/3**; ISSUE-0010 retains its operational failure. Current-local-revision Linux amd64 checks have not been rerun. Earlier CI successes refer to their recorded revisions, not a later revision without its exact corresponding checks.

[HANDOFF-0143](archive/handoffs/HANDOFF-0143-structured-output-ports.md) records the implementation and exact evidence; [the sanitized receipt](../../evals/baselines/qualifications/qualification-structured-ports-2026-10-25.json) records its narrow scope. The documentation migration's [handoff](archive/handoffs/HANDOFF-0144-documentation-layout.md) distinguishes its prose-only checks from those runtime results.

## Record conventions

Put a bounded plan in `active/` with its goal, scope, decisions, commands, actual results and blockers. Keep failed and unrun checks. Move completed plans to `archive/plans/`; handoffs to `archive/handoffs/`; resolved issues to `archive/issues/`; historical reviews to `archive/reviews/`. Update this index and relative links in the same change. Work state must distinguish proposed, implemented and qualified behavior.

Do not commit raw `.runs/`, `.state/`, private diagnostics, credentials, model reasoning or unredacted evidence. A sanitized receipt must preserve unknown metrics as unknown and must not turn skipped discovery, denied execution or mocked dependencies into qualification. Publishing, deployment and issue closure remain subject to the user's current authorization.
