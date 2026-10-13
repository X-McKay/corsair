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

Prepare SPEC-0059 for review; implementation steps below are proposed, not started. The user selected language/framework-specific resource organization for detailed specification, not an application rollout. Documentation base: main4efad96 after PR66/69. Preserve fixed graph, native factories, operator authority and host non-execution.

Before experiments: reconcile PR49, the authoring package migration under PLAN-0056, actual framework metadata and relevant PR44/63 behavior. New image availability alone does not qualify authoring. Drafting and structural design can proceed while live gates remain blocked.

## Steps

- [x] Inspect current contracts, source, package convention, idea and evaluation policy; check record IDs against main and open toolchain/diagnostics PRs.
- [x] Draft resource ownership, selector input and outcomes, packaging/delivery bounds, identity, resume behavior and validation strategy.
- [ ] Review SPEC-0059 with the user; record accepted scope and any changes. Keep spec/plan draft until then.
- [ ] Pin reconciled authoring baseline; characterize failure classes/variation and record experiment size, thresholds, provider budget and mode limits before candidate evaluation.
- [ ] If needed, land authoring package migration independently with unchanged offered surface and existing checks.
- [ ] Implement agent-local profile selection and immutable delivery; test actual request/packaging/identity/error boundaries. Do not add deferred loading or new tool authority.
- [ ] Extract or write one reviewed pytest reference; compare with baseline on frozen development cases using make eval AGENT=authoring. Retain exact differences and all attempts.
- [ ] If justified, test one inert synthetic asset as a separate treatment; verify framework/source-convention and injection controls.
- [ ] Confirm the selected candidate on protected held-out data; run affected native serialization/replay and admitted frozen-patch sandbox checks for claims requiring them. Missing prerequisites remain blocked, not simulated passes.
- [ ] Review promotion/rollback evidence, update identities and qualified-scope records; expand to another profile only after its consumer and evidence exist.

## Validation and progress

2026-10-13: specification only. Resources, selector, tools, dependencies, agent prompts and evaluation cases are unchanged. Source inspection found EnvironmentEvidence uses strings and current authoring/static evaluation is Python-specific, so normalization and future-framework limitations are explicit. The single-profile pilot cannot prove all-eager versus selected efficiency; that comparison is deferred until meaningful second-profile cases exist.

Validation: `UV_PROJECT_ENVIRONMENT=/home/al/git/corsair/.venv UV_CACHE_DIR=/tmp/corsair-spec-uv-cache make test-config` passed 1246 tests in 54.91 seconds, with one existing SDK event-loop deprecation warning and no failures. After the handoff and final prose edits, the focused development-workflow suite passed 5 checks; `git diff --check` is clean. No new live model, provider, sandbox, native worker, replay, behavioral comparison or baseline promotion is performed for this draft.

## Decisions and next action

Recommend deterministic eager inclusion of the selected resources, a mandatory shared core, explicit core-only unknown selection, and hard failure for broken selected resources. Keep existing native capability IDs and additive per-attempt identities; do not create a registry/receipt service. Next action is spec review, not runtime implementation. Any accepted changes must preserve attribution between content, asset and loading treatments.
