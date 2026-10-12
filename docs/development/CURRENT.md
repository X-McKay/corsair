# Current work

Updated: 2026-10-11. This is a navigation index; linked plans, issues and qualification reports carry the details. Verify git/source state when resuming.

| Work | State | Records |
| --- | --- | --- |
| Shared development workflow | Implemented; sixteen offline repository guards pass | [SPEC-0002](specs/SPEC-0002-development-workflow.md), [PLAN-0002](plans/PLAN-0002-development-workflow.md) |
| Native client smoke checks | Layout checks pass; Codex state directory is read-only and Claude is unavailable here | [ISSUE-0002](issues/ISSUE-0002-native-client-discovery.md) |
| Milestone 1A ordinary-pod platform subset | Implemented and live-qualified twice with confirmed cleanup; later admission recorded separately | [SPEC-0001](specs/SPEC-0001-local-platform-qualification.md), [PLAN-0001](plans/PLAN-0001-local-platform-qualification.md), [ISSUE-0001](issues/ISSUE-0001-nested-container-runtime.md) |
| Remaining Milestone 1A installation/storage/kernel | Implemented and qualified on two fresh clusters with namespace/PV/cluster cleanup; gateway 1B tracked separately | [SPEC-0003](specs/SPEC-0003-openshell-admission.md), [PLAN-0003](plans/PLAN-0003-openshell-admission.md), [admission report](../qualification/openshell-admission.md) |
| Milestone 1B gateway and identity | Implemented and qualified on two fresh clusters with full fixture/private-state/cluster cleanup | [SPEC-0004](specs/SPEC-0004-openshell-gateway-identity.md), [PLAN-0004](plans/PLAN-0004-openshell-gateway-identity.md), [gateway report](../qualification/openshell-gateway.md) |
| Alternate local runtime profiles | Deferred idea; no automatic repair or fallback | [IDEA-0001](ideas/IDEA-0001-local-runtime-profiles.md) |

Latest handoff: [HANDOFF-0006](handoffs/HANDOFF-0006-openshell-gateway-identity-qualified.md), with native installation/authentication, actual generated identity/mount and access-isolation evidence, retained failures and confirmed cleanup.

Current runtime gate: plan only a bounded 1C native lifecycle/execution/transfer slice using supported CLI/SDK APIs and immutable compatible artifacts. Ordinary-pod kind/Calico, remaining 1A storage/native-kernel admission and bounded 1B gateway/identity each passed on two clean clusters; their reports keep coverage separate. All clusters, fixtures/PVs, private gateway state and port-forwards from 1B are removed with confirmation. Full command/file-transfer/exit semantics, policy, toolchains, recovery, application adapters, PydanticAI and Temporal remain unqualified. Historical original network raw runs are absent; published source/record were verified without claiming their raw-log re-audit. The new affected CNI regression is retained and passed.
