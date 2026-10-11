# Native OpenShell toolchain qualification

Status: bounded native 1E qualified on 2026-10-11 on two independently created clusters, with confirmed original-ID cleanup. Scope is native 1E only on the selected Linux amd64 tuple. Preparation and offline guards are not OpenShell runtime qualification. See [SPEC-0007](../development/specs/SPEC-0007-openshell-toolchains.md), [PLAN-0008](../development/plans/PLAN-0008-openshell-toolchains.md) and the [runbook](../runbooks/openshell-toolchains.md).

## Selected artifacts and authority

The admitted [runtime lock](../../deploy/runtime-lock.yaml), original hard-requirement policy, chart, kernel, TLS/auth and CNI inputs are unchanged. Current primary APIs still report OpenShell 0.1.3, Agent Sandbox 1.0.6, kind 0.33.0 and Calico 3.33.0. Compatible Helm 3.22.0 remains admitted; latest 4.3.0 is not qualified. Prior six-run policy/source/raw evidence and published PR #6/exact-head CI were verified before edits. Historical original network raw files remain absent and are not claimed as re-audited; new exact-node prerequisites are retained for this slice.

| Artifact | Immutable selection |
| --- | --- |
| Official Python | 3.12.15 slim-bookworm, Linux amd64 manifest sha256:2ed6491b93cd49272ee6de2b5a38440c3448360322c089fc23e370722d74179d |
| Official Maven/Temurin | Maven 3.10.0 Temurin 17 noble, Linux amd64 manifest sha256:5394efaabc436795b507ca400aaf86311db03543072e0e87ae66c595965d4aed |
| Python packages | pytest 9.0.2, iniconfig 2.3.0, packaging 25.0, pluggy 1.6.0, Pygments 2.19.2; exact primary wheel SHA256 pins in [wheels.json](../../deploy/qualification/toolchains/python/wheels.json) |
| Cold Python diagnostic | six 1.17.0; exact direct wheel URL and SHA256 4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274 |
| Maven project | JUnit Jupiter 5.14.4; resources 3.3.1, compiler 3.14.1, Surefire 3.6.0; exact versions in [pom.xml](../../deploy/qualification/toolchains/java/pom.xml) |
| Prepared Python config/manifest | sha256:5b902bd32489aab8180e6db42e4b68de25335b1300509e455c8d523843c219f7 / sha256:85ae1c16f888870a4cafaa8f865aed546f7803e2fdaab93dbc5bbe39aa475808 |
| Prepared Java config/manifest | sha256:165b21e4907414e939493271c6975053e84924889e967e8f9b397fdbf7a15c35 / sha256:fbe0674092679f92ce3c5992cd7e34a4c7887f3ad475ed711ae70ea356d14e64 |

Primary provenance: official image records reference [Python source 2a3b794](https://github.com/docker-library/python/tree/2a3b794c223ab067d122719541cdd54a068732a5/3.12/slim-bookworm) and [Maven source 8ef234b](https://github.com/carlossg/docker-maven/tree/8ef234bed02d88f4edcc1907880f567db1362a76/eclipse-temurin-17-noble); package metadata comes from [PyPI pytest 9.0.2](https://pypi.org/project/pytest/9.0.2/) and [Maven Central JUnit 5.14.4](https://repo.maven.apache.org/maven2/org/junit/jupiter/junit-jupiter/5.14.4/). Selected upstream CLI/SDK source is e1f3c82; native CLI transfers/SDK execution and supported runtime trust-bundle injection are reused.

## Trusted preparation and retained attempts

Baseline: 61 offline guards passed before edits. Initial 70 guards passed before live dispatch; corrected final evidence logic has 84 passing guards. These guards reject incomplete native reports, wrong test identity/count, skips, version-only success, and client transport errors without fresh original-sandbox upstream evidence. They do not qualify OpenShell.

Native artifact preparation 692e54613e4345ffa27e5f1a69ba2139 passed both actual no-network UID10001 projects. Python uses offline require-hashes installation. Maven uses native strict upstream checksums during trusted online preparation, then offline execution. Its 141 JAR/POM hashes have inventory SHA256 6d0d27e1332baa9b316785a7df10d588a4b53ce1465a3504361fd28e8304ecd7; repository metadata/prefixes are additionally frozen by the whole image digest. Original Python/Java control containers 7e003ca0732ddb6ef3d746eff29b873f551184d5c227517522c64424e458e820 and 02235649f31b8f2aaeb51898f8210b379609f3bd155e14aa32d9b48dea6e0de0 are confirmed absent. Both loaded manifests match trusted configs and unchanged fixture-source hashes. Images were loaded locally, never pushed to a registry.

Every failed run below remains failed. Each used fresh owned resources, acknowledged SDK calls and confirmed original Sandbox/CR/pod/PVC/PV, endpoint/gateway namespace, private-state and forward cleanup. No partial run contributes acceptance.

| Run | JUnit seconds / SDK calls | Producing layer and correction |
| --- | --- | --- |
| toolchain-host-001 | 167.305 / 14 | Python offline matrix passed; strict ordinary-pod Service control failed curl7 after mutation of the existing echo Service. Dependency/Java coverage unaccepted. Use a separate unavailable Service; do not infer a precise underlying cause |
| toolchain-host-002 | 156.930 / 21 | Cold six/import, PyPI 404/resolver and available transport passed; oracle assumed HTTP-forward502 but native client closed with RemoteDisconnected. Required native event was not exported before deletion; original-ID postmortem CRI/container lookup also failed. Missing event coverage stays unaccepted |
| toolchain-host-003 | 156.232 / 21 | Event exported, but oracle expected transparent-listener wording; actual mediated socket event says Proxy connection error. Require actual native event fields and destination identity |
| toolchain-host-004 | 140.409 / 7 | Host oracle editing mistake parsed the correct fixture checksum as an IP. Restore exact checksum comparison; no toolchain acceptance |
| toolchain-host-005 | 169.400 / 21 | Fresh original-sandbox connection-refused event and destination matched; client reported socket read TimeoutError instead of RemoteDisconnected. Accept either client detail only with unchanged native event/identity/freshness requirements and deadlines |
| toolchain-host-006 | 163.950 / 11 | Actual Java compilation/JUnit passed; missing-artifact oracle required the word offline. Native Maven prefix restriction produced DependencyResolutionException. Require that actual diagnostic and keep the upstream filter enabled |

Original failed sandbox IDs, per-command receipts and source revisions remain in .runs/toolchain-resume/failed-host-001-audit.json through006, source-revision-002 through007, and the reconstructed hash-matching failed-host-001-source.py. All 95 failed-run SDK calls were acknowledged. Run002's missing event cannot be reconstructed from the retained client exception. Inspection mistakes and corrections are retained separately in history.json. No failed image preparations occurred in this slice.

## Final-source qualification

The unchanged admitted tuple is Linux 6.14.0-37-generic, containerd 2.3.4, Kubernetes 1.35.8 and Landlock ABI6. Both nodes passed actual storage persistence/cleanup and every mandatory native capability field before OpenShell installation. Each also passed all three ordinary-pod CNI tests with two fixture namespace/readiness/cleanup records.

| Node UID | Admission / JUnit seconds | CNI / JUnit seconds |
| --- | --- | --- |
| a8df054f-96d3-4bef-9757-1f63e0e3097b | toolchain-admission-001 / 94.418 | toolchain-network-001 / 158.905 |
| 564bd544-bfe5-4404-b64b-365a597cd498 | toolchain-admission-002 / 98.334 | toolchain-network-002 / 158.161 |

Each complete invocation used fresh native gateway TLS/auth/identity controls, one Java and one Python sandbox, and identical immutable artifacts. Both source freezes match current source. Actual native versions, JUnit test IDs/counts, deliberate failures, cold download, permitted PyPI404/resolver and fresh matching registry-failure events were reconciled from raw commands/SDK output.

| Run | JUnit seconds | SDK / native commands | Original Java / Python IDs |
| --- | --- | --- | --- |
| toolchain-host-007 | 230.439 | 36 / 183 | f492118d-108d-4dc7-9007-da64b91fc580 / ba6403a0-6a74-40db-a2da-b1b579897290 |
| toolchain-host-008 | 257.710 | 36 / 211 | f819d84b-a279-4f3e-a358-cad6d9d2dfff / 8bfdabbd-6b3c-4d59-8b03-fc0bf114d0d8 |

All original Sandbox/CR/pods/PVC/PVs, endpoint and gateway namespace/PVs, private gateway state and forwards are confirmed removed. Final owned inventories toolchain-final-inventory-001/002 are empty. Both immutable original cluster IDs are confirmed absent, and owner/kubeconfig/private state are absent. Cached images remain inert artifacts.

| Run | Original gateway namespace / PV UID | Endpoint namespace UID |
| --- | --- | --- |
| toolchain-host-007 | e3c202e9-20a2-4a2c-aaff-f8d80c8a84ac / cc4baff7-fab6-4482-9ad5-12444ee3a269 | ff963f75-9fff-47a4-92a3-52c7f88f630f |
| toolchain-host-008 | 56ef388a-9411-421d-a3e5-b14e9322b3d6 / c6f9512f-3794-4761-b50d-b030b69decc4 | 9fbddda8-3dee-4da0-9967-c799aa2357e8 |

| Node | Original cluster container ID | Native absence audit |
| --- | --- | --- |
| 001 | 6ad7897cd69b45f629db895a253ebc52d3a73ff4fb191f6fbddc6a4bc1b49577 | .runs/toolchain-resume/cluster-001/audit.json |
| 002 | fb9206dd1379ee1da798151c5ac6510525968e3e221e58b8d80e176501b57554 | .runs/toolchain-resume/cluster-002/audit.json |

Final 84 offline guards pass; eight live tests collect with one toolchain selection and no dispatch. Compilation and diff checks pass. The two runs observed 72 acknowledged SDK calls, 394 native commands and 46721 UTF-8 SDK stdout/stderr bytes. Native registry event IDs 07571d75-278c-48ba-90d6-6927f909ffa2 / 867b9db5-ca40-4154-8773-bbbb543a21b3 match fresh original-sandbox/destination evidence. These are host observations; internal retries/queue timing remain unknown.

Final source freezes, all raw acceptance/failure receipts, prerequisites and cluster absence were reconciled in .runs/toolchain-resume/final-evidence-audit.json, final-source-hashes.json, prerequisites-audit.json and failed-attempts-audit.json. Probe SHA256 2c426a735099991bc4d0055b1563cf65a0639a53b72a8f201efcfa8b5e2b6dd0; preparation SHA256 2978449e8759ee0fedc66cc65fd30b77bb09c1dcbb218dc9a05264bb9fdc3549. No functional source changed between the two accepted runs.

## Required matrix and attribution

Native CLI stages only the fixed trusted project files; native SDK execution confirms every transferred hash. Actual running imageID must match the selected immutable manifest. Existing gateway controls prove TLS/auth/identity/access isolation; workload identity is UID10001, no capabilities/privilege escalation, no attached providers and isolated native workspace storage. No production adapter or kubectl workload execution fallback.

Both warmed offline language matrices precede the separate network stage. Python 3.12.15/pytest9.0.2 executes test_native.test_native_roundtrip with native JUnit count1/zero skips, then independent syntax/collection exit2, no-discovery exit5 and assertion exit1. Temurin17.0.20.1+1/javac17.0.20.1/Maven3.10.0 compiles and executes corsair.NativeTest.nativeRoundtrip with native JUnit count1/zero skips, then independent resolver, no-discovery, compilation and assertion failures. Native reports are reconciled against retained SDK output and exact expected identifiers; a version string never establishes execution.

Maven -o uses the frozen cache and no network grant. The synthetic absent artifact produces the native Central namespace-prefix rejection plus DependencyResolutionException. It establishes an attributable dependency-resolver diagnostic, not a registry404 or policy denial. Maven 3.10's [native repository prefix filtering](https://maven.apache.org/components/resolver-archives/resolver-LATEST/remote-repository-filtering.html) remains enabled; this source does not claim a generic cache-miss diagnostic or arbitrary Maven cold resolution.

The separate cold Python policy allows enforced REST GET only to the exact six wheel path, exact missing-package path, available echo Service and separate unserved Service, with exact hostname/port and local Service /32 restrictions. TLS verification/interception remains enabled through native trust injection. Full/base/global authority, empty providers and loaded policy revisions are retained. A fresh no-cache/no-deps require-hashes six install must import from the new target directory. An actual permitted PyPI404 and pip resolver exit1 are separate receipts. Available registry transport must return200; trusted ordinary-pod Pod/Service probes confirm the unserved port returns curl7.

Unavailable registry acceptance requires native client exit1 with close/read-timeout detail AND a new nonempty event UID absent from the before-request snapshot, original sandbox UID, class_uid4001/activity_id4/status_id2, exact Proxy connection error: Connection refused (os error 111), and the client-observed mediated destination IP/port5679. Any fresh policy-denial event rejects acceptance. Supervisor logs are exported before deletion even on failure. Client timeout alone cannot qualify; this is an upstream transport diagnostic, not 1F interruption coverage. Network/command/create deadlines and hard policy/TLS/kernel requirements are unchanged.

## Review and supported limits

Source/artifact/evidence review corrected all listed oracle findings before final-source acceptance. Native evidence and failure history remain local under ignored .runs/; credentials/private gateway state are never published. Resolve the tracked source with git log -1 --format=%H -- docs/qualification/openshell-toolchains.md and compare raw source hashes when resuming.

This is bounded native 1E on one Linux amd64 host and two independently created single-node clusters. It cannot establish production tenancy, fleet/multi-node behavior, other architectures, arbitrary Python/Maven registries, application framework/security cases or general escape resistance. 1F interruptions/limits/recovery, adapters, PydanticAI and Temporal remain unqualified. Earlier native admission delays near140–142s remain observed with unknown cause; this slice does not establish a reliability repair. Host call counts, command elapsed times and bytes are retained; internal retries/queue timing are unknown. No agent/model/provider telemetry exists, and missing telemetry is not zero.
