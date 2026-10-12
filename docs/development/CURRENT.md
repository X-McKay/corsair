# Current work

Updated: 2026-10-11. This is a navigation index; linked plans, issues and qualification reports carry the details. Verify git/source state when resuming.

| Work | State | Records |
| --- | --- | --- |
| Shared development workflow | Implemented; fourteen offline repository guards pass | [SPEC-0002](specs/SPEC-0002-development-workflow.md), [PLAN-0002](plans/PLAN-0002-development-workflow.md) |
| Native client smoke checks | Layout checks pass; Codex state directory is read-only and Claude is unavailable here | [ISSUE-0002](issues/ISSUE-0002-native-client-discovery.md) |
| Milestone 1A ordinary-pod platform subset | Implemented and live-qualified twice with confirmed cleanup; later admission recorded separately | [SPEC-0001](specs/SPEC-0001-local-platform-qualification.md), [PLAN-0001](plans/PLAN-0001-local-platform-qualification.md), [ISSUE-0001](issues/ISSUE-0001-nested-container-runtime.md) |
| Remaining Milestone 1A installation/storage/kernel | Implemented and qualified on two fresh clusters with namespace/PV/cluster cleanup; gateway uninstalled | [SPEC-0003](specs/SPEC-0003-openshell-admission.md), [PLAN-0003](plans/PLAN-0003-openshell-admission.md), [admission report](../qualification/openshell-admission.md) |
| Alternate local runtime profiles | Deferred idea; no automatic repair or fallback | [IDEA-0001](ideas/IDEA-0001-local-runtime-profiles.md) |

Latest handoff: [HANDOFF-0005](handoffs/HANDOFF-0005-openshell-admission-qualified.md), including selected immutable artifacts, two-fresh-cluster native probe/storage results, retained failures and confirmed cleanup.

Current runtime gate: plan a bounded 1B gateway/identity slice using the selected OpenShell v0.1.3 chart/images and Helm v3.22.0, with native Agent Sandbox discovery preflight enabled, verified TLS/local access isolation and actual generated identities/mounts. Ordinary-pod kind/Calico and the remaining 1A installation/storage/native-kernel boundaries each passed twice; reports preserve their separate coverage. All clusters and fixtures from this session are deleted. Full sandbox lifecycle, policy, toolchains, recovery, application adapters, PydanticAI and Temporal remain later unqualified work. Historical raw network runs are absent here; the published record/source were verified without claiming a raw-log re-audit.
