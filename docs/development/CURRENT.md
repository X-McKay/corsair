# Current work

Updated: 2026-10-11. This is a navigation index; linked plans, issues and qualification reports carry the details. Verify git/source state when resuming.

Current focus: review simplicity and organization before further retry/reconciliation work. Native application transfers remain blocked; independent local source/artifact qualification does not admit sandbox storage integration. No live cluster or OpenShell installation remains; private evidence is retained separately.

| Active or latest work | State | Records |
| --- | --- | --- |
| Milestone 2 native transfers | Blocked before application/live dispatch: supported retry and bounded extraction admission unresolved | [SPEC-0011](specs/SPEC-0011-native-transfer-admission.md), [PLAN-0013](plans/PLAN-0013-native-transfer-admission.md), [ISSUE-0006](issues/ISSUE-0006-native-transfer-retry-admission.md) |
| Milestone 2 local source/artifacts | Qualified for one exclusive local root and complete offline bare Git repository; principles review recorded | [SPEC-0012](specs/SPEC-0012-immutable-source-artifacts.md), [PLAN-0014](plans/PLAN-0014-immutable-source-artifacts.md), [report](../qualification/local-source-artifacts.md) |
| Native client discovery | Layout checks pass; actual client smoke checks remain limited | [ISSUE-0002](issues/ISSUE-0002-native-client-discovery.md) |

Latest handoff: [HANDOFF-0016](handoffs/HANDOFF-0016-principles-and-organization-review.md). [HANDOFF-0015](handoffs/HANDOFF-0015-source-artifacts-qualified-transfer-blocked.md) preserves the local source qualification and transfer investigation.

| Qualified foundation | Evidence and limits |
| --- | --- |
| Native platform and OpenShell 1A–1F | [Network](../qualification/network-platform.md), [admission](../qualification/openshell-admission.md), [gateway](../qualification/openshell-gateway.md), [lifecycle/transfers](../qualification/openshell-lifecycle.md), [Service controls](../qualification/service-readiness.md), [policy](../qualification/openshell-policy.md), [toolchains](../qualification/openshell-toolchains.md), [recovery](../qualification/openshell-recovery.md) |
| Readiness characterization | [Readiness report](../qualification/openshell-readiness.md): original 120s local budget is historical; separate native-default observation is not a product SLO. Corrected full 1F matrix remains unrun. |
| Application lifecycle and bounded execution | [Lifecycle adapter](../qualification/openshell-adapter-lifecycle.md), [execution adapter](../qualification/openshell-adapter-execution.md): selected operator-exclusive workspace and Linux/glibc profile only; live fault/cancellation coverage remains incomplete. |

Each fresh runtime still needs mandatory storage/kernel/CNI/gateway admission. Full Milestone 2, agents, PydanticAI/Temporal integration and production reliability remain unqualified. Reports retain failed/unknown attempts, missing historical evidence and immutable cleanup facts; completed record history remains under [development records](README.md). [Alternate runtime profiles](ideas/IDEA-0001-local-runtime-profiles.md) remain deferred with no fallback.
