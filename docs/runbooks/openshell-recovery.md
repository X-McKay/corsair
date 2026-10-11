# Native OpenShell interruption and limit qualification

Run only on the dedicated owned Linux amd64 cluster, with fixed immutable 1E Python artifacts and the admitted hard policy. These are destructive trusted infrastructure probes, not application finding/fix tests. See [SPEC-0008](../development/specs/SPEC-0008-openshell-recovery.md) and [PLAN-0009](../development/plans/PLAN-0009-openshell-recovery.md).

```shell
UV_OFFLINE=true make test-config
make kind-up
make admission-install
make toolchain-images-load
make qualify-admission CORSAIR_QUAL_RUN=.runs/recovery-admission-NEW
make qualify-network CORSAIR_QUAL_RUN=.runs/recovery-network-NEW
make openshell-install CORSAIR_ADMISSION_RUN=.runs/recovery-admission-NEW
make qualify-recovery CORSAIR_NETWORK_RUN=.runs/recovery-network-NEW CORSAIR_QUAL_RUN=.runs/recovery-host-NEW
make kind-down
```

Never reuse a prior evidence directory or bypass a failed exact-node prerequisite. Artifact preparation is separate; successful 1E cache/config/manifest/source receipts must still match. Every attempt captures native SDK/CLI/Kubernetes detail and frozen source. Native timeout124 and backend I/O74 may be synthetic; retain all client terminals as acknowledged delivery with remote completion unknown. Distinguish an acknowledged client terminal status from unknown remote completion. The fixed exclusive operation marker and original PID/start-ticks prevent an unobserved replay from qualifying. Inspect remote process liveness separately, then delete the original native sandbox and confirm CR/pod/PVC/PV and original container-task absence.

The test client uses native exec_stream and retains only its explicit byte budget. Overflow closes that native client and leaves completion unknown; it does not qualify arbitrary-output memory limits in the SDK, which accumulates chunks internally. The producing fixture itself has a finite output bound. Client loss intentionally terminates only the owned host client process. Gateway restart deletes only the identity-checked owned StatefulSet pod, confirms a replacement UID/readiness and TLS/auth/health, explicitly closes the owned old forward, opens a replacement forward/native TLS client, waits original-ID sandbox readiness within 120s, reobserves original PVC/PV UIDs and never resends the workload operation. Both original and replacement local forwards remain owned by the gateway fixture until namespace cleanup.

OOM uses an actual 128Mi native memory request/limit and a finite maximum 192Mi allocation. Native original-container OOMKilled evidence is mandatory; allocation exceptions or generic SDK transport errors cannot qualify. Each normal sandbox has a real execution control before interruption; all original resource identities and cleanup remain attributable. Export diagnostics before deletion. Before cluster removal, retain an empty owned-resource inventory and original immutable Docker ID; confirm its absence afterward. Repeat the complete unchanged-source matrix on a second independently created cluster before claiming native 1F or assessing full native Milestone1 closure.


The [reviewed final report](../qualification/openshell-recovery.md) closes bounded native 1A–1F on this tuple. If native readiness exceeds its unchanged 120-second deadline, keep the attempt failed, capture partial original identities/logs before deletion, confirm cleanup, and follow [ISSUE-0004](../development/issues/ISSUE-0004-native-admission-readiness.md). Do not treat a later successful matrix as a reliability repair or automatically retry that possible side effect.
