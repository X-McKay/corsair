---
id: PLAN-0064
kind: plan
title: Framework-specific skill resources pilot
status: draft
updated: 2026-10-13
related: [SPEC-0059, IDEA-0007, PLAN-0056, PLAN-0048]
---

# Framework-specific skill resources pilot

## Objective and dependencies

Prepare SPEC-0059 for review; implementation steps below are proposed, not started. The user selected language/framework-specific resource organization for detailed specification, not an application rollout. Revised source/base: main497db9f (2026-10-13), after merged PR49/44/51/55 and related runtime/toolchain work. Preserve fixed graph, native factories, operator authority and host non-execution.

Before experiments: pin the merged authoring/planner behavior, reconcile authoring migration under PLAN-0056, and pin relevant PR63 setup behavior. Use runtime selection plus versioned matrix/framework identity; G12 must carry it into production authoring, with explicit operator fixture identity permitted for the isolated pilot. New image availability alone does not qualify authoring. Drafting and structural design can proceed while live gates remain blocked.

## Steps

- [x] Inspect current contracts, source, package convention, idea and evaluation policy; check record IDs against main and open toolchain/diagnostics PRs.
- [x] Draft resource ownership, selector input and outcomes, packaging/delivery bounds, identity, resume behavior and validation strategy.
- [ ] Review SPEC-0059 with the user; record accepted scope and any changes. Keep spec/plan draft until then.
- [ ] Author and freeze an expanded development set and a separate protected held-out set before candidate measurement. Preserve existing collection-correction cases and fill missing behavioral strata; keep held-out data out of tuning and resource authorship.
- [ ] Pin reconciled authoring baseline and remeasure it on the new dataset digests (old scores are incomparable); characterize failure classes/variation and record experiment size, thresholds, provider budget and mode limits before candidate evaluation.
- [ ] If needed, land authoring package migration independently with unchanged offered surface and existing checks.
- [ ] Characterize actual entry-point token limits and baseline headroom, measure rendered input tokens, and freeze common arm budgets/request envelope/response reserve. Shrink resources to fit (8 KiB each, 16 KiB rendered total ceilings); insufficient capacity blocks candidate measurement pending operator review and rebaselining. Report token exhaustion separately.
- [ ] Verify the native RunContext instruction callback and activity/worker resolution seam, compact dependency identity, exact digest checks and actual repeated model-request/history bytes. No history-deduplication claim without evidence; durable adoption stays blocked if the seam is unavailable.
- [ ] Update package convention and scaffold guidance for references/assets in the implementation PR. Keep selector/map/renderer in prompts.py and one shared factory.
- [ ] Implement agent-local profile selection and immutable delivery; test actual request/packaging/identity/error boundaries. Do not add deferred loading or new tool authority.
- [ ] Add resource_catalogue_sha256 to evals/run.py IDENTITY and configuration metadata; record per-case bundle/delivery digests in existing native attributes, including unknown coverage.
- [ ] Extract or write one reviewed pytest reference preserving plain-assert, witness protection and current authored-file read behavior; compare with baseline on frozen development cases using make eval AGENT=authoring. Retain exact differences and all attempts.
- [ ] If justified, test one inert synthetic asset as a separate treatment; verify framework/source-convention and injection controls.
- [ ] Confirm the selected candidate on protected held-out data; run affected native serialization/replay and admitted frozen-patch sandbox checks for claims requiring them. Missing prerequisites remain blocked, not simulated passes.
- [ ] Review promotion/rollback evidence, update identities and qualified-scope records; expand to another profile only after its consumer and evidence exist.

## Validation and progress

2026-10-13: specification only. Resources, selector, tools, dependencies, agent prompts and evaluation cases are unchanged. Initial inspection found EnvironmentEvidence uses strings and current authoring/static evaluation is Python-specific. The review revision below replaces the proposed normalization with existing runtime admission evidence. The single-profile pilot cannot prove all-eager versus selected efficiency; that comparison is deferred until meaningful second-profile cases exist.

Validation: `UV_PROJECT_ENVIRONMENT=/home/al/git/corsair/.venv UV_CACHE_DIR=/tmp/corsair-spec-uv-cache make test-config` passed 1246 tests in 54.91 seconds, with one existing SDK event-loop deprecation warning and no failures. After the handoff and final prose edits, the focused development-workflow suite passed 5 checks; `git diff --check` is clean. No new live model, provider, sandbox, native worker, replay, behavioral comparison or baseline promotion is performed for this draft.

## Decisions and next action

Recommend deterministic eager inclusion of the selected resources, a mandatory shared core, explicit core-only unknown selection, and hard failure for broken selected resources. Keep existing native capability IDs and additive per-attempt identities; do not create a registry/receipt service. Next action is spec review, not runtime implementation. Any accepted changes must preserve attribution between content, asset and loading treatments.


## Review revision

Revised after the substantive PR70 feedback. Runtime selection replaces prose normalization; no invented framework row ID or second version-support table. Chose measured token headroom with equal frozen arm budgets, compact durable identity with explicit native payload verification, separate frozen development/held-out datasets and rebaselining. Named the native callback/package seam, catalogue/case identities, smaller bounds and existing authoring semantics. PR49's own-file read now returns the latest admitted write; not_in_source applies only outside both inventories. Original validation above remains historical; no experiment or runtime implementation is implied by this revision.

Review revision checks: bare `python` was unavailable for the initial edit script; reran it with the existing Python 3.12 virtualenv. Final record/link checks passed 5 tests; diff check clean. Full offline `make test-config` on the main497db9f integration passed 1381 tests in 78.15 seconds, one existing SDK event-loop warning. Final record checks cover the later handoff/prose updates. No live or behavioral experiment was run.

## Main reconciliation after follow-up review

Verified the four follow-up points at 575168f: measured token headroom with equal budgets, admitted matrix-row selection, compact durable identity with native serialization verification, and frozen development/held-out sets before candidate measurement. Merged main e090d27 while preserving both the draft resource-spec row and all newer main rows in CURRENT.md. Removed one duplicate catalogue-identity checkbox. Prior source and validation paragraphs are historical snapshots; SPEC-0059 and this plan remain draft. No runtime implementation, experiment, scope acceptance or baseline promotion occurred. Follow-up validation is recorded below.

Follow-up checks: `UV_PROJECT_ENVIRONMENT=/tmp/corsair-pr70-review-venv UV_CACHE_DIR=/tmp/corsair-provider-uv-cache make test-config` passed 1618 tests in 90.26 seconds with one existing SDK event-loop deprecation warning. PR diff against main passes `git diff --check`; the merge-index check also saw an existing trailing blank line in main's PLAN-0070, left unchanged. PR73 now uses HANDOFF-0090; main uses HANDOFF-0087 for planning, so the earlier 0083/0086 collisions are resolved. No live checks were needed for the documentation reconciliation.
