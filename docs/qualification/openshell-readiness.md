# Native default readiness observation

Date: 2026-10-11. **Six samples passed on two fresh owned nodes with confirmed full cleanup.** See [PLAN-0010](../development/plans/PLAN-0010-native-readiness-sample.md), [ISSUE-0004](../development/issues/ISSUE-0004-native-admission-readiness.md) and [runbook](../runbooks/openshell-adapter-lifecycle.md).

## Scope and provenance

Three fresh fixed-image sandboxes per node use the actual pinned SandboxClient.wait_ready default 300s, with no readiness override. Neither 300 nor the old 120 budget is an upstream guarantee or product SLO. The [native source](https://github.com/NVIDIA/OpenShell/blob/e1f3c82caa3ed3b65de22889ae7ef32a774878ef/python/openshell/sandbox.py) and installed source SHA-256 57b9450b6b514a90f994d03fdb8a2b52d3d23d35560f66e7e2100d09ec7814cb agree. Context7 supplied discovery/documentation; pinned source and actual receipts establish behavior.

All [runtime-lock](../../deploy/runtime-lock.yaml), policy/TLS and mandatory storage/kernel/CNI controls remain selected. Linux amd64 6.14.0-37-generic/Docker 29.8.2/containerd 2.3.4, kind 0.33.0/Kubernetes 1.35.8/Calico 3.33.0, Agent Sandbox 1.0.6/OpenShell 0.1.3/Helm 3.22.0. Primary release APIs checked before edits confirm selected OpenShell/Agent Sandbox latest; Helm 4.3.0 exists but is not adopted. Fixed qualified Python image manifest 85ae1c16f888870a4cafaa8f865aed546f7803e2fdaab93dbc5bbe39aa475808, config 5b902bd32489aab8180e6db42e4b68de25335b1300509e455c8d523843c219f7; actual requests/limits CPU 1/512Mi. Native pod/secret/host/capability checks, accepted policy/config identity, hard Landlock, original IDs and real Python execution control are mandatory in each sample.

## Measurements and cleanup

First node 55d0bd9e-f471-45d2-96fe-03eaefb0feb5: adapter-admission-001 passed 93.171s; actual remount retained original PVC/PV identity, native capability probe exit 0 reported all 18 booleans true, UID/GID 10001 and ABI 6. adapter-network-001 passed 3/158.381s with positive Service/Pod controls, deny/rollback and fixture cleanup. adapter-readiness-001 passed 1/257.750s including gateway controls and cleanup; 21 explicit SDK method receipts. Create times 0.186/0.182/0.170s; wait_ready times 142.237/9.015/8.014s. The read-only pending observation recorded Kubernetes Ready while native wait was pending; Kubernetes readiness was never substituted for native readiness.

Each sandbox's original CR/workload/supervisor UID, PVC/PV UID, manifest, policy and two container IDs are retained with disappearance checks. Gateway namespace/PV/private state and forward cleanup passed. Final inventory was empty, then original cluster container 7f1b92d184ef408f1daf602cdfa0039379e6e79578bba634ab4e8d0fdc4f9559 was confirmed absent; owner/kubeconfig/private state absent. Raw source/JUnit/native receipts and independent audits are ignored under .runs/adapter-* and .runs/lifecycle-adapter-resume/. Frozen source-v1 binds each run; first sampler used the original ownership helper, then its sole change added an optional operator name for adapter reuse. Default native behavior is unchanged; do not claim identical helper bytes across the two sample runs.

## Retained failures and interpretation

Direct offline collection first failed due to read-only default uv cache, before runtime delivery; explicit repository UV_CACHE_DIR collected successfully. First admission command accidentally reused historical .runs/lifecycle-admission-001. The empty-directory guard refused cluster work, but pytest overwrote its old JUnit summary with the new setup-error report. Other original evidence remains. No fabricated restoration; copied error and availability loss recorded under .runs/lifecycle-adapter-resume/admission-directory-collision*. New admission/network Make guards refuse an existing directory before pytest starts. The replacement fresh run used adapter-admission-001. These are operator/evidence failures, not native admission failures.

Historical recovery 002/009 remain failed under 120s, with eventual readiness unknown; none is relabeled. Historical 1F pass records retain their original source/budget. New first fresh wait 142.237s demonstrates why the old budget could exclude an otherwise admitted fixture, without establishing the cause or counterfactual outcome of earlier failures. Later faster observations are sequence measurements, not proof of a cold-cache cause. Internal polling/RPC/retry/controller queue telemetry remains unknown. No product SLO is invented and this small sample cannot establish fleet reliability. Full corrected 1F interruption matrix has not been rerun by this sample.

## Second node and bounded conclusion

Second node c40e33c1-2e70-45e7-b7b5-54403ff071dc: adapter-admission-002 passed 93.103s; adapter-network-002 passed 3/156.693s, with native kernel/remount and CNI controls plus confirmed cleanup. adapter-readiness-002 passed 1/121.968s, 21 explicit SDK method observations. The three waits were 8.014/8.015/9.017s; all actual Ready/profile/policy/image/control and resource checks passed. Gateway namespace/PV/private/forward cleanup passed. Final inventory empty and original cluster aadcdd22652bea044e6848b9ceb8f54ca605146e944ffad6b1a54800021b41ef confirmed absent, with private/owner/kubeconfig state absent.

| Run / sample | Original native ID | Create seconds | Native readiness seconds |
| --- | --- | --- | --- |
| adapter-readiness-001/1 | 30eef47b-5221-47b3-b2a9-f66ae53b1c41 | 0.186 | 142.237 |
| adapter-readiness-001/2 | d7b216aa-e1a6-4ecb-b440-221d1db23e7e | 0.182 | 9.015 |
| adapter-readiness-001/3 | 3ac5e811-5992-4f9e-985f-e101abe7e2e3 | 0.170 | 8.014 |
| adapter-readiness-002/1 | 4bae18be-9040-4981-a003-f13c6338532e | 0.176 | 8.014 |
| adapter-readiness-002/2 | 57b77840-82de-4ca3-ba3d-481bf31c8cf0 | 0.171 | 8.015 |
| adapter-readiness-002/3 | bece3cf6-3a5d-4253-906a-597e9d6458aa | 0.165 | 9.017 |

Independent runs-audit-001/002 and cluster-001/002 audits match raw JUnit, native observations, original IDs and frozen source. Six normal waits ranged from 8.014 to 142.237s. ISSUE-0004 is resolved as a bounded characterization and operational decision: use the pinned native default, require actual Ready/security admission for every new runtime, retain failures and investigate a future timeout, and defer a product SLO until a product requirement exists. Cause and fleet reliability remain unknown. This closes the observation without claiming an upstream repair.
