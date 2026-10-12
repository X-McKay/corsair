---
id: ISSUE-0004
kind: issue
title: Native sandbox startup latency is uncharacterized
status: open
updated: 2026-10-11
related: [SPEC-0008, PLAN-0009, ISSUE-0003]
---

# Native sandbox startup latency is uncharacterized

## Observed and expected behavior

Recovery-host-002/009 failed to observe native sandbox readiness within our local 120-second test budget. That observation remains valid; it does not establish an OpenShell defect or breach of an upstream readiness guarantee. The cause and eventual readiness of those specific attempts are unknown because original-identity cleanup followed the timeout. Actual Ready state and security admission are still required before workload use. The ordinary-pod Service prerequisite is a separate resolved boundary; no causal identity with ISSUE-0003 is established.

The 120-second override first appeared in Corsair's 1C test at commit cc97b88 and was carried into 1D/1F. An [upstream SDK example](https://github.com/NVIDIA/OpenShell/blob/e1f3c82caa3ed3b65de22889ae7ef32a774878ef/docs/sdk/python.mdx#L87) uses 120, and the higher-level Sandbox wrapper defaults to 120. Our actual SandboxClient.wait_ready API has a [300-second default](https://github.com/NVIDIA/OpenShell/blob/e1f3c82caa3ed3b65de22889ae7ef32a774878ef/python/openshell/sandbox.py#L1111). No user requirement, recorded startup SLO or measured rationale established 120 as mandatory. The user authorized correcting this attribution and using the pinned API default for future native readiness waits. This is a test-budget correction; neither 120 nor 300 is an upstream readiness guarantee.

## Reproduction and evidence

The selected Linux amd64 tuple passed actual storage/kernel/CNI controls. Runs 002/009, their SDK errors, source revisions, partial original CR/pod/PVC/PV/container identities, supervisor logs and confirmed cleanup remain ignored under .runs/recovery-resume/ and their original run directories. [The report](../../qualification/openshell-recovery.md) preserves their failed results and the two accepted original-source 1F matrices. Earlier successful policy creates took approximately 140–142s within their separate 180-second CLI budget. These observations demonstrate variable startup timing; they do not identify its cause.

## Attempts and diagnosis

Run 009 logs show supervision starting without an observed gateway policy-fetch message before teardown. Immutable upstream source performs boundary image-policy discovery before that fetch; DiscoverPolicy/Attach has a separate five-minute backend request budget. This suggests a possible startup stage but does not establish actual cause, retry count or a network failure. The backend budget is distinct from the SDK readiness default. No unknown workload was replayed, runtime patched or security requirement relaxed.

## Resolution criteria and next action

The earlier resolution criteria treated the harness deadline as a mandatory runtime criterion and demanded a supported repair. That interpretation is withdrawn. The four explicit 120-second SandboxClient.wait_ready overrides now use the pinned API's 300-second default. Original run results are never relabeled, and there is no claim that the failed attempts would have passed at 300 seconds. The corrected harness has not been live requalified. The known functional qualification remains attributable to source 4aacc8a and its original 120-second budget.

This record stays open as a startup-latency observation, rather than a demonstrated upstream defect or an automatic Milestone 2 blocker. Next: collect a bounded fresh-native readiness sample using the actual API default, retaining timings, native state and original-ID cleanup for every attempt. Define an operational startup SLO only if a product requirement needs one. Close the observation when its characterization and operational decision are documented; do not infer fleet reliability from a small sample. If actual native Ready is not reached within the supported bounded wait, keep that attempt failed and investigate before using that runtime. Planning the next component can proceed; speculative host/CNI patches, automatic repair and unknown-command replay remain excluded.
