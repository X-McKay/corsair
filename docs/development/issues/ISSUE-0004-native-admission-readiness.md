---
id: ISSUE-0004
kind: issue
title: Native sandbox startup latency observation
status: resolved
updated: 2026-10-11
related: [SPEC-0008, PLAN-0009, ISSUE-0003, PLAN-0010]
---

# Native sandbox startup latency observation

## Observed and expected behavior

Recovery-host-002/009 failed to observe native sandbox readiness within our local 120-second test budget. That observation remains valid; it does not establish an OpenShell defect or breach of an upstream readiness guarantee. The cause and eventual readiness of those specific attempts are unknown because original-identity cleanup followed the timeout. Actual Ready state and security admission are still required before workload use. The ordinary-pod Service prerequisite is a separate resolved boundary; no causal identity with ISSUE-0003 is established.

The 120-second override first appeared in Corsair's 1C test at commit cc97b88 and was carried into 1D/1F. An [upstream SDK example](https://github.com/NVIDIA/OpenShell/blob/e1f3c82caa3ed3b65de22889ae7ef32a774878ef/docs/sdk/python.mdx#L87) uses 120, and the higher-level Sandbox wrapper defaults to 120. Our actual SandboxClient.wait_ready API has a [300-second default](https://github.com/NVIDIA/OpenShell/blob/e1f3c82caa3ed3b65de22889ae7ef32a774878ef/python/openshell/sandbox.py#L1111). No user requirement, recorded startup SLO or measured rationale established 120 as mandatory. The user authorized correcting this attribution and using the pinned API default for future native readiness waits. This is a test-budget correction; neither 120 nor 300 is an upstream readiness guarantee.

## Reproduction and evidence

The selected Linux amd64 tuple passed actual storage/kernel/CNI controls. Runs 002/009, their SDK errors, source revisions, partial original CR/pod/PVC/PV/container identities, supervisor logs and confirmed cleanup remain ignored under .runs/recovery-resume/ and their original run directories. [The report](../../qualification/openshell-recovery.md) preserves their failed results and the two accepted original-source 1F matrices. Earlier successful policy creates took approximately 140–142s within their separate 180-second CLI budget. These observations demonstrate variable startup timing; they do not identify its cause.

## Attempts and diagnosis

Run 009 logs show supervision starting without an observed gateway policy-fetch message before teardown. Immutable upstream source performs boundary image-policy discovery before that fetch; DiscoverPolicy/Attach has a separate five-minute backend request budget. This suggests a possible startup stage but does not establish actual cause, retry count or a network failure. The backend budget is distinct from the SDK readiness default. No unknown workload was replayed, runtime patched or security requirement relaxed.

## Resolution criteria and next action

The earlier resolution criteria treated the harness deadline as a mandatory runtime criterion and demanded a supported repair. That interpretation is withdrawn. The four explicit 120-second SandboxClient.wait_ready overrides now use the pinned API's 300-second default. Original run results are never relabeled, and there is no claim that the failed attempts would have passed at 300 seconds. The complete corrected 1F interruption matrix has not been rerun; the separately recorded native readiness sample passed. The known functional qualification remains attributable to source 4aacc8a and its original 120-second budget.

Resolved after the authorized [bounded readiness sample](../../qualification/openshell-readiness.md): three actual native-default waits on each of two fresh admitted nodes, with original-resource and full private/cluster cleanup. Waits 142.237/9.015/8.014s and 8.014/8.015/9.017s characterize only this fixture. No cause, fleet guarantee or upstream defect/repair is established. Original failed 120s attempts retain unknown eventual readiness and their original results. Full corrected 1F interruption matrix remains unrerun; this sample does not relabel historical qualification.

Operational decision: retain the pinned 300s native default, require actual Ready and mandatory security controls for each runtime, retain and investigate future timeouts before workload use, and create a product SLO only when a product requirement needs one. These measurements and decision satisfy this observation’s resolution criteria. This closes the repository observation, not an external issue or production reliability claim. Automatic repairs, policy weakening and blind replay remain excluded.
