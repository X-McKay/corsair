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

## SPEC-0045: JDK 8 image and per-image gates (2026-10-13)

[SPEC-0045](../development/specs/SPEC-0045-jdk8-toolchain-and-junit4.md) adds the `java8` image, puts the pinned JUnit Platform console launcher 1.14.4 (SHA-256 7c6968cbcaf4301c729f202b23b7d736c5d88be625fc7d27ad5d746146a8bc28, Java 8 class files) and maven-dependency-plugin 3.8.1 in both Java images, and splits the gate into one test per image under one module-scoped gateway. Run on RIG0 in the worktree `.worktrees/claude-toolchain-jdk8-junit4-x5k2l4`, on a fresh cluster that worktree created (kind node container dd6cd613…, Kubernetes 1.35.8, Calico ready). Commands, every attempt and the corrections are in [PLAN-0049](../development/plans/PLAN-0049-jdk8-toolchain-and-junit4.md).

| Artifact | Immutable selection |
| --- | --- |
| Official Maven/Temurin 8 | `maven:3.10.0-eclipse-temurin-8` index sha256:f2cb52730ea0bde9dc8ba20e5e539d000dcdd7ab9e498d70c301fe04fbddb656; docker-library source [docker-maven 4bcc1de](https://github.com/carlossg/docker-maven/tree/4bcc1dea6507fba8ec40c602bf1bfdb963e21288) (official-images library file on 2026-10-13; the tag's directory is not recorded per digest) |
| Prepared images (ed57d13 build) | java8 config sha256:b48b90862a6860d60f9b3fa6de1e9a3db9a8d9e460c4f7b281cb4529dbe8f02c; java config sha256:e23aaf05…; python config sha256:68f08d0e… (full digests in each image's `.cache/toolchains/<dir>/image.json` on RIG0) |
| Measured in the java8 sandbox | javac 1.8.0_504, Temurin 1.8.0_504-b01, Maven 3.10.0, JUnit 4.13.2 under Surefire 3.6.0 through the Vintage engine |

Admission `qual-admission` 1 passed (89 s) and network `qual-network` 3 passed (169 s) at 3cb0bc6, both under the worktree's `.runs/jdk8-toolchain-20261013/`, reused for the final gate on the same node. Final gate `qual-toolchain-2` at 3ad3755, one attempt, 3 passed, 454 s; pytest root pinned to the worktree by the Makefile:

| Gate | Seconds | Sandbox id | In-sandbox checks |
| --- | --- | --- | --- |
| java8 | 154 | 7f85f8b8-94c8-400b-98d5-187516514f95 | runner discovery and execution argv (junit-vintage, both `corsair.NativeTest` methods), missing artifact (native Maven prefix resolver), no discovery, compilation, assertion |
| java | 172 | 869db6a6-322e-4f01-bf6d-e021915d272c | the same through junit-jupiter |
| python | 127 | 40acfe48-1ba5-4642-bde3-ec25618f3528 | syntax/collection, no discovery, assertion, dependency diagnostics |

The shared gateway passed TLS, caller auth, identity and access isolation (probe sandbox 450b97d7-42b6-4589-b9fe-d3fad1295c00); every sandbox's cleanup and the gateway uninstall, PV reclamation, private-state removal and port-forward stop were confirmed. After this run, #55's CPython 3.7 gate was merged in as a fourth gate on the same module-scoped gateway. The three gates were rerun on merged main 93a0fab (`qual-toolchain-main`, `TOOLCHAINS="java8 java python"`, same node, admission and network reused, one attempt): 3 passed, 429 s; java8 152 s (sandbox a55e1cfc-0a45-4778-90f9-a0ba5620d11e), java 142 s (5f654327-c87b-4a4a-8cf6-00672b4b5309), python 134 s (bd0c63c7-2d48-42ea-abb7-a636a9167b4d); shared gateway controls passed (probe 477c4ec3-95ea-4925-aeea-6e6d8d7bc719); every sandbox, endpoint namespace, the gateway, PV, private state and port-forward confirmed removed. The matrix rows rest on this run. The 3.7 gate has its own live run.

Real case, image-only (Docker on RIG0, not OpenShell): VUL4J-6 (commons-compress, JUnit 4.12, Surefire 2.19.1) through `MavenRunner` in a `--network=none`, capability-dropped container of the java8 image. The control is a Corsair-authored copy of `ZipShortTest#testToBytes` added to Vul4J's `Test_CVE_2018_1324`, whose PoV method stays byte-identical. Fix revision: both ids listed, control and PoV passed (8.8 s). Vulnerable revision with the fix's test file: control passed, PoV `TestTimedOutException` after 6000 ms, the CVE-2018-1324 loop hitting the test's own timeout (11.8 s). This qualifies JUnit 4.12 with the runner on this image; it is not sandbox evidence.

Not established: JUnit 4 before 4.12 (no Vintage discovery), any JUnit 4 or 5 version other than those listed, JDK 8 under other Maven versions, a checked-in expected Maven cache manifest for either Java image (follow-up), and the SPEC-0042 benchmark report, whose matrix input predates these rows.

## SPEC-0046: CPython 3.7 image, real case and witness v2 probe (2026-10-13)

[SPEC-0046](../development/specs/SPEC-0046-cpython37-toolchain.md) adds the `python37` image and pytest 6 to 7 support in the runner, parser and probe. Run on RIG0 in the worktree `.worktrees/claude/toolchain-python37-drklks`, on a fresh cluster that worktree created after `make kind-down` in the JDK 8 worktree. Commands, every attempt and the corrections are in [PLAN-0050](../development/plans/PLAN-0050-cpython37-toolchain.md). Evidence is under the worktree's `.runs/` and archived to `/home/al/git/corsair/.runs/py37-toolchain-20261013/` on RIG0.

| Artifact | Immutable selection |
| --- | --- |
| Official CPython 3.7 | `docker.io/library/python@sha256:b53f496ca43e5af6994f8e316cf03af31050bf7944e0e4a308ad86c001cf028b` (`3.7-slim`, Debian 12) |
| Prepared image | `corsair-python37:40be61014c031922`, config sha256:86f897d206b1efda625eb1654b2f30ea4c69214318810f66b861c4238620ade9, node manifest sha256:b8e51f30c0d928f809d91c360bcb20a5cf3672af444959f4f5a900c7040b29ca |
| Measured in the sandbox | Python 3.7.17 (GCC 12.2.0), pytest 7.4.4 |

Network `py37-network-20261013T131142Z` (3 passed) and admission `py37-admission-20261013T131451Z` (1 passed) at 93a0fab, reused for every gate on the same node. `make openshell-install` ran before each gate, because each gate's cleanup removes the gateway and its private state.

| Gate | Commit | Run | Result |
| --- | --- | --- | --- |
| `qualify-toolchain TOOLCHAINS=python37` | 794a003 (93a0fab plus #86) | `py37-toolchain-20261013T133347Z` | 1 passed, 188.4 s; sandbox 13ca59c6-0a85-4a33-99e9-e41786232f3e; shared gateway TLS, caller auth, identity and access isolation passed (probe sandbox 03ed858f-c421-4f94-bc75-393b7219f562); 21 observed SDK calls, internal retries unknown |
| `qualify-python37-case` (CVE-2021-32839) | 4117e3f (794a003 plus #88) | `py37-case-20261013T134635Z` | 1 passed, 104.4 s; baseline (9.38 s, cs-951ee7603f9557ab) and fix (11.63 s, cs-c3e8b75027f65ce3) each discovered exactly the two planned ids, completed with native exit 0 and 2 passed; witness captured and refused by name: `witness probe unsupported on this runtime: CPython 3.7.17 has no sys.monitoring (3.12+)` |
| `qualify-witness` | 4117e3f | `py37-witness-20261013T134900Z` | 1 passed, 146.7 s on the 3.12 image; probe digest c89e0d65181b78daa2f729b91f550ffa14cde45868a5daaf0ddb62e25cb43eb6 (`corsair-witness-v2` as of 4117e3f; main's probe later changed under #44 to 64d21d9d…, not gated) |

Every sandbox, the gateway, PV, private state and port-forward were confirmed removed after each gate. Failed attempts are retained:
- `py37-toolchain-20261013T131750Z` (93a0fab): the cold-install check asserted an absolute `six.__file__`; CPython 3.7 keeps a module's `__file__` relative when imported through a relative `sys.path` entry. The check now inserts an absolute entry (#86).
- `py37-toolchain-20261013T133252Z` (794a003): setup error, gateway `owner.json` missing, because the previous gate's cleanup had removed the gateway; `make openshell-install` was rerun first.
- `py37-case-20261013T133724Z` (794a003): discovery found no admitted ids, because the patch carried the whole upstream `tests/test_format.py` (about 60 tests, some parametrized). The patch now keeps the module's imports and only the two planned methods, copied line for line (#88).

Assessment eval on the regenerated v2 set, scripted, development: `20261013T135139Z-development-scripted`, 51/51 clean, mean repeat agreement 1.0, dataset sha256 22773b81…; promoted as the scripted development baseline (no earlier run with this set and mode).

The matrix rows `cpython-3.7-pytest` and pytest `==6.0.2 || ==6.2.5 || ==7.0.1 || ==7.2.0 || ==7.4.4` on it rest on these runs; 7.4.4 ran in the sandbox, the other versions rest on real output on 3.7.17 checked offline. The CVE-2021-32839 run is not a disposition: the upstream test is functional and passes at both commits.

Not established: pytest below 6.0 (4.6 and 5.4 reject `--import-mode=importlib`), witness observation on 3.7 (refused by design), the probe now on main (64d21d9d…, changed by #44 after these runs; the case and witness gates ran with c89e0d65…), dependency installation for real 3.7 cases (the environment agent's setup), and the SPEC-0042 benchmark report, which needs fetched trees to regenerate. Reselecting the stored requirements in `benchmarks/runtime-requirements.json` against the new matrix moves 15 revisions of 9 Python cases from unsupported to `cpython-3.7-pytest`; that is a selection check, not a regenerated report.
