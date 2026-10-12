# Current work

Updated: 2026-10-11. This is a navigation index; linked plans, issues and qualification reports carry the details. Verify git/source state when resuming.

Current focus: corrected native1F, bounded completed execution-output storage, original SDK-worker loss and result-receipt refusal are qualified on two fresh admitted nodes with original cluster cleanup. Native controlled upload remains qualified; untrusted download/application transfer admission remains blocked. Next bounded action is source-upload consumer/writer review under PLAN-0013. The withdrawn Docker staging profile stays withdrawn.

| Active or latest work | State | Records |
| --- | --- | --- |
| Corrected native1F | Qualified on two fresh nodes using native readiness default and unchanged requirements | [SPEC-0008](specs/SPEC-0008-openshell-recovery.md), [PLAN-0009](plans/PLAN-0009-openshell-recovery.md) |
| Remaining execution boundaries | Qualified: bounded stdout/stderr-to-artifacts, actual original worker loss and result-receipt EACCES; broader recovery remains unqualified | [SPEC-0010](specs/SPEC-0010-sandbox-execution-adapter.md), [PLAN-0012](plans/PLAN-0012-sandbox-execution-adapter.md), [report](../qualification/openshell-adapter-execution.md) |
| Milestone 2 native transfers | Controlled native upload qualified; application retry and untrusted bounded extraction admission blocked | [SPEC-0011](specs/SPEC-0011-native-transfer-admission.md), [PLAN-0013](plans/PLAN-0013-native-transfer-admission.md), [ISSUE-0006](issues/ISSUE-0006-native-transfer-retry-admission.md), [upload report](../qualification/openshell-native-upload.md) |
| Milestone 2 local source/artifacts | Qualified for one exclusive local root and complete offline bare Git repository; principles review recorded | [SPEC-0012](specs/SPEC-0012-immutable-source-artifacts.md), [PLAN-0014](plans/PLAN-0014-immutable-source-artifacts.md), [report](../qualification/local-source-artifacts.md) |
| Native client discovery | Layout checks pass; actual client smoke checks remain limited | [ISSUE-0002](issues/ISSUE-0002-native-client-discovery.md) |

Latest handoff: [HANDOFF-0019](handoffs/HANDOFF-0019-openshell-execution-boundaries-qualified.md). [HANDOFF-0018](handoffs/HANDOFF-0018-native-upload-qualified.md) retains controlled upload qualification. [HANDOFF-0017](handoffs/HANDOFF-0017-native-transfer-course-correction.md) preserves the staging course correction; [HANDOFF-0015](handoffs/HANDOFF-0015-source-artifacts-qualified-transfer-blocked.md) preserves local source qualification.

| Qualified foundation | Evidence and limits |
| --- | --- |
| Native platform and OpenShell 1A–1F | [Network](../qualification/network-platform.md), [admission](../qualification/openshell-admission.md), [gateway](../qualification/openshell-gateway.md), [lifecycle/transfers](../qualification/openshell-lifecycle.md), [Service controls](../qualification/service-readiness.md), [policy](../qualification/openshell-policy.md), [toolchains](../qualification/openshell-toolchains.md), [recovery](../qualification/openshell-recovery.md) |
| Readiness characterization | [Readiness report](../qualification/openshell-readiness.md): original 120s local budget is historical; separate native-default observation is not a product SLO. Corrected full1F subsequently passed on two further fresh admitted nodes. |
| Application lifecycle and bounded execution | [Lifecycle adapter](../qualification/openshell-adapter-lifecycle.md), [execution adapter](../qualification/openshell-adapter-execution.md): selected operator-exclusive workspace and Linux/glibc profile only; bounded live worker/result-receipt and output-storage cases passed; controller/transport/durability/cancellation coverage remains incomplete. |

Each fresh runtime still needs mandatory storage/kernel/CNI/gateway admission. Full Milestone 2, agents, PydanticAI/Temporal integration and production reliability remain unqualified. Reports retain failed/unknown attempts, missing historical evidence and immutable cleanup facts; completed record history remains under [development records](README.md). [Alternate runtime profiles](ideas/IDEA-0001-local-runtime-profiles.md) remain deferred with no fallback.
