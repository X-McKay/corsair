# Current work

Updated: 2026-10-10. This is a navigation index; linked plans, issues and qualification reports carry the details. Verify git/source state when resuming.

| Work | State | Records |
| --- | --- | --- |
| Shared development workflow | Implemented; ten offline checks pass | [SPEC-0002](specs/SPEC-0002-development-workflow.md), [PLAN-0002](plans/PLAN-0002-development-workflow.md) |
| Native client smoke checks | Layout checks pass; Codex state directory is read-only and Claude is unavailable here | [ISSUE-0002](issues/ISSUE-0002-native-client-discovery.md) |
| Milestone 1A platform subset | Implemented; live qualification blocked on nested host prerequisites | [SPEC-0001](specs/SPEC-0001-local-platform-qualification.md), [PLAN-0001](plans/PLAN-0001-local-platform-qualification.md), [ISSUE-0001](issues/ISSUE-0001-nested-container-runtime.md) |
| Alternate local runtime profiles | Deferred idea; no automatic repair or fallback | [IDEA-0001](ideas/IDEA-0001-local-runtime-profiles.md) |

Latest handoff: [HANDOFF-0001](handoffs/HANDOFF-0001-development-workflow.md).

Current runtime gate: all three live ordinary-pod platform/CNI checks on a compatible host, confirmed cleanup, and a second clean cluster creation/run. See the [qualification record](../qualification/network-platform.md). Actual OpenShell kernel/storage admission, gateway and later components remain pending. Do not integrate unqualified runtime components; independent planning/research and offline fixes can continue.
