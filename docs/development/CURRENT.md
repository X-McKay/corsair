# Current work

Updated: 2026-10-11. This is a navigation index; linked plans, issues and qualification reports carry the details. Verify git/source state when resuming.

| Work | State | Records |
| --- | --- | --- |
| Shared development workflow | Implemented; ten offline checks pass | [SPEC-0002](specs/SPEC-0002-development-workflow.md), [PLAN-0002](plans/PLAN-0002-development-workflow.md) |
| Native client smoke checks | Layout checks pass; Codex state directory is read-only and Claude is unavailable here | [ISSUE-0002](issues/ISSUE-0002-native-client-discovery.md) |
| Milestone 1A ordinary-pod platform subset | Implemented and live-qualified twice with confirmed cleanup; OpenShell admission remains pending | [SPEC-0001](specs/SPEC-0001-local-platform-qualification.md), [PLAN-0001](plans/PLAN-0001-local-platform-qualification.md), [ISSUE-0001](issues/ISSUE-0001-nested-container-runtime.md) |
| Alternate local runtime profiles | Deferred idea; no automatic repair or fallback | [IDEA-0001](ideas/IDEA-0001-local-runtime-profiles.md) |

Latest handoff: [HANDOFF-0004](handoffs/HANDOFF-0004-kind-calico-qualified.md), including the qualified host tuple, two-clean-cluster evidence, retained failures and a copyable next-slice prompt.

Current runtime gate: select compatible immutable Agent Sandbox, OpenShell, Helm and workload artifacts, then implement the bounded remaining 1A installation/storage/kernel-runtime admission slice. The ordinary-pod kind/Calico prerequisite passed twice with confirmed fixture and cluster cleanup; see the [qualification record](../qualification/network-platform.md). OpenShell gateway and later components remain pending. Do not integrate unqualified runtime components.
