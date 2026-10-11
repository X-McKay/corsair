# Current work

Updated: 2026-10-11. This is a navigation index; linked plans, issues and qualification reports carry the details. Verify git/source state when resuming.

Current focus: the documented trusted single-file native upload passed on two fresh admitted nodes with confirmed cleanup. Native application transfers and untrusted download admission remain blocked; next is a focused documented-download admission review. The premature Docker staging experiment remains withdrawn, with failures retained in PLAN-0013. No live cluster or OpenShell installation remains; private evidence is retained separately.

| Active or latest work | State | Records |
| --- | --- | --- |
| Milestone 2 native transfers | Controlled native upload qualified; application retry and untrusted bounded extraction admission blocked | [SPEC-0011](specs/SPEC-0011-native-transfer-admission.md), [PLAN-0013](plans/PLAN-0013-native-transfer-admission.md), [ISSUE-0006](issues/ISSUE-0006-native-transfer-retry-admission.md), [upload report](../qualification/openshell-native-upload.md) |
| Milestone 2 local source/artifacts | Qualified for one exclusive local root and complete offline bare Git repository; principles review recorded | [SPEC-0012](specs/SPEC-0012-immutable-source-artifacts.md), [PLAN-0014](plans/PLAN-0014-immutable-source-artifacts.md), [report](../qualification/local-source-artifacts.md) |
| Native client discovery | Layout checks pass; actual client smoke checks remain limited | [ISSUE-0002](issues/ISSUE-0002-native-client-discovery.md) |

Latest handoff: [HANDOFF-0018](handoffs/HANDOFF-0018-native-upload-qualified.md). [HANDOFF-0017](handoffs/HANDOFF-0017-native-transfer-course-correction.md) preserves the staging course correction; [HANDOFF-0015](handoffs/HANDOFF-0015-source-artifacts-qualified-transfer-blocked.md) preserves local source qualification.

| Qualified foundation | Evidence and limits |
| --- | --- |
| Native platform and OpenShell 1A–1F | [Network](../qualification/network-platform.md), [admission](../qualification/openshell-admission.md), [gateway](../qualification/openshell-gateway.md), [lifecycle/transfers](../qualification/openshell-lifecycle.md), [Service controls](../qualification/service-readiness.md), [policy](../qualification/openshell-policy.md), [toolchains](../qualification/openshell-toolchains.md), [recovery](../qualification/openshell-recovery.md) |
| Readiness characterization | [Readiness report](../qualification/openshell-readiness.md): original 120s local budget is historical; separate native-default observation is not a product SLO. Corrected full 1F matrix remains unrun. |
| Application lifecycle and bounded execution | [Lifecycle adapter](../qualification/openshell-adapter-lifecycle.md), [execution adapter](../qualification/openshell-adapter-execution.md): selected operator-exclusive workspace and Linux/glibc profile only; live fault/cancellation coverage remains incomplete. |

Each fresh runtime still needs mandatory storage/kernel/CNI/gateway admission. Full Milestone 2, agents, PydanticAI/Temporal integration and production reliability remain unqualified. Reports retain failed/unknown attempts, missing historical evidence and immutable cleanup facts; completed record history remains under [development records](README.md). [Alternate runtime profiles](ideas/IDEA-0001-local-runtime-profiles.md) remain deferred with no fallback.
