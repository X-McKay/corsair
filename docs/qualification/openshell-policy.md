# OpenShell native policy qualification

Status: bounded native 1D qualified on 2026-10-11: three complete fresh-sandbox repetitions on each of two independently created single-node clusters on this Linux amd64 host, with confirmed original-resource/private-state/cluster cleanup. [SPEC-0006](../development/specs/SPEC-0006-openshell-policy.md), [PLAN-0007](../development/plans/PLAN-0007-openshell-policy.md) and the [runbook](../runbooks/openshell-policy.md) define the scope. Toolchains 1E, recovery 1F, production tenancy, adapters, PydanticAI and Temporal remain unqualified.

## Source and selected artifacts

Clean base 4222a60a0eb99a65eaaa43a02e641381e5c28881 matched published draft PR #5; branch codex/openshell-1d-policy. Prior actual native 1C/gateway/cleanup and final Service-readiness receipts were read, with summaries retained in .runs/policy-resume/prior-evidence-audit.json. This does not claim re-audit of absent historical original network raw logs.

Primary latest release APIs on 2026-10-11 retain OpenShell v0.1.3/e1f3c82caa3ed3b65de22889ae7ef32a774878ef, Agent Sandbox v1.0.6, kind v0.33.0 and Calico v3.33.0. Compatible admitted Helm 3.22.0 remains selected; latest 4.3.0 is unadmitted. The existing [runtime lock](../../deploy/runtime-lock.yaml), SDK/dependency lock, original identity policy, TLS/auth/chart/CNI/kernel settings are unchanged. Immutable primary schema/SDK/CLI/proxy/isolation source bytes match the extracted source, retained under .runs/policy-resume/.

The operator-only [Dockerfile](../../deploy/qualification/policy-image/Dockerfile) derives from the fixed upstream Ubuntu digest43c1682f… and copies the fixed official curlimages/curl digest9a1ed35a… into isolated library paths, adding two harmless canaries. No dependency resolution, copied OpenShell runtime, image registry publication or loader environment override. Native library search-path configuration and two relative libcurl symlinks relocate that fixed binary without replacing Ubuntu libraries. Both test policies grant only that library directory read-only, keeping the excluded canary disjoint. Native no-network Docker build, UID10001 DAC/content/executable controls and kind load bind Dockerfile/config/containerd manifest identity. Actual running image ID is mandatory; preparation/version output alone never qualifies policy.

Final artifact: .runs/policy-image/cf5d492bafa94142b3d0dc9afb281d75/, config sha256:84e58098c371ecb4b6228f58b1b03737b7b69f3fc0625d3c1115ade24ad57ad9, Dockerfile SHA256: 22b2d26a01012f0265d039d570c742e0734c0a4b99aa2eace6e9491249817098, loaded manifest sha256:0664fcb5e7aee1ea247f4c3b0aeba2146f3f7fac356601fd63aa00cfaa5becb9. Native controls actually invoke curl 8.14.1, not merely readlink. Successful and failed control container identities and absence are retained.

## Retained attempts and failure layers

| Attempt | Result | Attribution and cleanup |
| --- | --- | --- |
| policy-host-001, gateway install8965474f68034923a9236b86a5af7bda | 1 failed/80.04s before policy endpoint/sandboxes | Fresh gateway returned explicit native NotFound/no global policy revision found. Corrected the oracle to record confirmed absence while rejecting other lookup failures. Gateway controls and original namespace/PV/private/forward cleanup passed |
| policy-host-002, install47d86a080ffe443ea476c09ee47347d8 | 1 failed/291.02s | Filesystem control and all three filesystem denials passed; first network control sdk0013 exited127 because Ubuntu has no curl. No network pass/denial claim. Original sandbox/CR/pod/PVC/PV, endpoint and gateway cleanup confirmed |
| policy-host-003 | 1 failed / 192.42s | Filesystem and native GET/POST controls passed, but denial preceded JSON logger activation. Native shorthand denial retained; required JSON evidence incomplete. All original-ID sandbox/volume/endpoint/gateway/private/forward cleanup confirmed |
| policy-host-004 | 1 failed / 183.08s | All 13 native proxy requests passed with five new JSON endpoint denials; NetworkPolicy evidence oracle incorrectly required explicit empty egress rather than the native omitted empty field. No complete matrix pass claimed; all original-ID cleanup confirmed |
| Image74b3cbb7d9fa4d6db9e75fb4da7a4108 | Native executable control failed127 | Copied absolute libcurl symlink no longer resolved; original control a04ebbaf4aa77f92ed7d62fb8c46c39200bc2de3d16f767343bca68ec4497fb8 absent |
| Imaged64836b403aa4e00a8891836dcf0218a | Native executable control failed127 | Retained unsuccessful loader-path attempt; native read-only diagnostic established absolute symlink failure. Original control ID/absence retained |

The canary-only initial image9b5ac13e2a63450eb6e10c31e6588b67 and first-node manifest32d8b91a… remain retained as unqualified network artifacts. Initial readlink -f succeeds even for a nonexistent final executable; corrected preparation requires test -x plus invocation. Original trusted control418552007d196380d11cf3a9a2571e34f3bac43c19794805fd36dbdd2dc777d1 has native create/start/die/destroy events and original-ID absence. Both failed image controls and a read-only loader diagnostic have confirmed immutable cleanup. Prior images/caches remain inert evidence artifacts.

Second attempt gateway create took142.286s within the unchanged180s native-command budget. Read-only native observations found workload Pod Ready but supervisor not Ready and native admission pending; gateway logged kube client SendRequest failure before eventual admission. Their causal relationship remains unknown. This is an observed latency/transport-warning limit, not a recovery/reliability qualification. No create command was replayed or deadline extended.

First investigation node storage/kernel policy-admission-001 passed91.45s; policy-network-001 passed3 tests/155.76s. No network failure was counted as denial. Final empty owned namespace/Sandbox/PVC/PV inventory policy-final-inventory-001 and identity-checked kind teardown confirmed; owner/kubeconfig removed. Read-only absent-path/template/browser/audit mistakes and corrections are retained in .runs/policy-resume/history.json. Pinned Kubernetes networking API v0.35.8 declares empty egress rules with omitempty. With explicit Egress isolation, omitted and empty rules both deny all; the corrected oracle rejects actual grants, null and missing isolation. This changes only evidence interpretation, never the installed policy. Six guards cover these native forms and failures. Original ordinary-pod Service timeout remains individually unattributed as recorded in ISSUE-0003; its bounded admission correction is separate.

Second-node policy-host-008/010 restrictive creates took 141.55s/140.18s within the unchanged 180-second budget. Native read-only observations retained workload readiness with supervisor readiness pending, and, for run008, the log interval from supervision start at 17:20:05.172 to policy fetch/enforcement/load at 17:22:25.906–25.937 UTC. The original command completed without replay. The cause remains unknown; full recovery and latency qualification are outstanding.

## Final-source qualification

Mandatory native prerequisites passed before gateway/policy work on both distinct nodes. The admitted tuple is Linux 6.14.0-37-generic, containerd 2.3.4, Kubernetes 1.35.8 and Landlock ABI 6, with every required capability-probe field true.

| Node UID | Admission run / JUnit seconds | CNI run / JUnit seconds | Cleanup |
| --- | --- | --- | --- |
| a548d1a3-a504-4a89-a538-e3ab5e6e29c7 | policy-admission-002 / 91.295 | policy-network-002 / 158.588 | Namespace/PV and both CNI fixtures confirmed |
| 793c0bc0-2135-4bda-b783-577b84510fdd | policy-admission-003 / 91.288 | policy-network-003 / 159.482 | Namespace/PV and both CNI fixtures confirmed |

Each following invocation passed the complete matrix in two fresh original-ID policy sandboxes, with fresh gateway TLS/auth/identity controls and endpoint. All running workloads matched the same immutable manifest.

| Run | Node | JUnit seconds | SDK / native calls | Original control / restricted IDs |
| --- | --- | --- | --- | --- |
| policy-host-005 | 002 | 247.482 | 29 / 251 | f10700b8-9faa-4bcb-92b3-7dcba056813c / 9cd98a00-e4bd-4003-ad46-b9d2d72f7cd0 |
| policy-host-006 | 002 | 192.365 | 29 / 250 | 8b24a627-41df-4134-a832-a45f694b36e8 / 431d77d8-1028-43f6-b872-13a8460ca1a8 |
| policy-host-007 | 002 | 194.755 | 29 / 258 | 81eb648f-ba71-4134-8a42-d57fda0f1bb3 / ff0f5390-1ef8-4e98-8c99-c15a77101b5a |
| policy-host-008 | 003 | 321.733 | 29 / 251 | 995b8cae-1422-44b2-80e4-3c3c51eaec54 / 98ecea1e-eacb-426c-8d62-bca801d53c63 |
| policy-host-009 | 003 | 192.288 | 29 / 250 | 169212dd-e03c-430c-8a03-1acbe6b4e492 / da696d88-4be6-4ccd-9f8e-25dd17dcce32 |
| policy-host-010 | 003 | 323.681 | 29 / 250 | 3e209082-2dbf-4688-a666-167d8cf7a215 / 316c916f-4604-4ffc-8a85-57d8abda73c2 |

Each run has 13 native proxy requests, five positive server markers, ten denied markers including two outer-CNI routes, five new matching JSON endpoint-denial events bound to the original restricted sandbox, and loaded policy revisions 1/2/3. Actual SDK method-denial details, native direct-CNI receipts and final server logs were reconciled, rather than accepting summaries alone. Every original Sandbox/CR/pod/PVC/PV, endpoint and gateway/private/forward cleanup is confirmed.

| Run | Original gateway namespace UID / PV UID | Original endpoint namespace UID |
| --- | --- | --- |
| policy-host-005 | 45e3f77c-6a93-4d5e-b8b0-39185065978c / 2cc9ccfd-80a2-4dab-8dd1-b6c6745de808 | 127a6486-8818-46fe-9b95-fd997d1851bb |
| policy-host-006 | 7433427b-e381-4ba2-a834-49bfd0dae647 / 3ffd1cd3-6232-49d8-8f7a-5ed56f22594c | 6543daa2-b19e-4244-a9dc-510a39f908d1 |
| policy-host-007 | feed20fb-0420-4c54-8e91-1b60b96518a5 / 2a88abd8-c931-41c3-ba71-ddb1fafbb59d | f69c6d10-d3aa-4cfa-bf8d-485e8be26c73 |
| policy-host-008 | 573c82a1-6848-4959-a235-fdb56956c0d4 / d9814a30-6103-4226-8976-5445685fa3d7 | af9b61c3-999d-4d74-aeb7-2d33a9ed374a |
| policy-host-009 | def00955-b283-45ca-8c2a-85d77474f07c / 326d7a88-7cff-44fa-b68b-4ccf38e91a15 | 2b4a178f-7007-4992-9a9c-9fe256947425 |
| policy-host-010 | 6089364d-6c30-4026-a4b1-33ae83dc8a28 / 93c94418-38ff-4f95-a3a7-131109a71554 | c9c78542-4821-45e7-8228-f3721f37fa27 |

Both final owned namespace/Sandbox/PVC/PV inventories are empty: .runs/policy-final-inventory-002/ and 003/. Identity-checked cluster removal is confirmed:

| Node | Original container ID | Native cleanup evidence |
| --- | --- | --- |
| 002 | 612818bfa963572a56f1938645451bb0436a7ffedea73c26732dd08229e7fb1a | .runs/bootstrap/6145b910223d4d699f180a12d854665c |
| 003 | a43cd765332a51a93dc05ac6164267ce4fbf912f7dc4a5cfb1562fcfb9df0b3f | .runs/bootstrap/34d3020ff1384c5eb9276da5ab73e397 |

Owner/kubeconfig, private gateway state and forwards are absent. Cached images remain inert artifacts. Source hashes in .runs/policy-resume/final-source-hashes-004.json match all six live runs and the current qualification/runtime inputs; complete raw receipts and audits remain local under .runs/, never Git. Resolve the committed source with git log -1 --format=%H -- docs/qualification/openshell-policy.md.

## Required matrix and evidence

Final-source repetitions, immutable identities, native evidence and cleanup were audited in .runs/policy-resume/final-evidence-audit.json, prerequisites-audit.json and failed-attempts-audit.json. Each fresh node must pass storage/kernel/CNI and gateway/identity before policy probes. Two static sandboxes share the same artifact; native creation ID binds every subsequent observation and deletion. Full/base/global policy, no providers, actual generated identities/mounts and loaded revisions are required. Native SDK performs execution/deletion/expected-ID waits; no application adapter or kubectl workload execution fallback.

Filesystem: permitted canary read/write with exact content and DAC 444/666; restrictive scratch read/write and read-only canary read; excluded read, scratch symlink read and read-only write denied with unchanged content. Kernel/controlled-image/native-operation facts attribute these observations; universal per-access Landlock logs are not claimed.

Network: exact endpoint hostname, Service /32, port 5678 and canonical curl with explicit GET/POST REST enforce. Initial GET/POST controls must succeed and reach server logs. Native policy set --wait narrows to GET and removes the endpoint; effective/loaded/hash identity must agree. Three narrowed POST and three absent-rule GET trials need continuing reachable trusted controls and denied-marker absence. Literal-IP and noproxy attempts require fresh matching OCSF transparent_tcp_policy_denied observations alongside native curl 7, destination/port and curl identity. Native scoped JSON logging changes observability only. A separate 30-second setup gate observes its atomic activation before traffic; a stored setting acknowledgment cannot admit probes. Read-only bounded log polling does not retry workload calls. Actual generated workload NetworkPolicy and trusted direct-pod Service/Pod route probes independently establish the outer CNI boundary.

Final policy/gateway/fixture/cleanup/JUnit/cluster identity records agree. Offline 61 guards pass; seven live tests collect without dispatch. The six policy invocations observed 174 completed SDK calls and 1,510 native commands, 30 positive and 60 denied network markers, and 30 distinct matching native JSON endpoint denials. Native JSON activation took 7.680–9.780s within its separate setup budget. Host SDK/native calls and elapsed times are observable; internal RPC/controller/transport retries and queue timing remain unknown. Missing telemetry is unknown, not zero. No model/provider/agent/durable calls are dispatched.

## Review and limits

Pre-policy review corrected original-create ID binding; its replacement guard requires retained original ID and no deletion of a replacement. Artifact/policy/error/loaded-state fail-closed guards distinguish missing executable, unavailable endpoint, wrong identity, audit authority and unrelated events. No policy, TLS, kernel or upstream pin was relaxed to obtain a pass. Final review corrected all mandatory findings before final-source acceptance; no unresolved mandatory finding remains.

This bounded matrix cannot establish production tenancy, fleet/multi-node consistency, other architectures or general escape resistance. Toolchains 1E and interruptions/limits 1F remain mandatory before full native Milestone 1 qualification; application adapters/agents/Temporal remain later work.

Primary sources: [release](https://github.com/NVIDIA/OpenShell/releases/tag/v0.1.3), [immutable schema](https://github.com/NVIDIA/OpenShell/blob/e1f3c82caa3ed3b65de22889ae7ef32a774878ef/docs/how-it-works/policies/schema.mdx), [native transparent enforcement](https://github.com/NVIDIA/OpenShell/blob/e1f3c82caa3ed3b65de22889ae7ef32a774878ef/crates/openshell-supervisor-network/src/proxy.rs), [native global NotFound](https://github.com/NVIDIA/OpenShell/blob/e1f3c82caa3ed3b65de22889ae7ef32a774878ef/crates/openshell-server/src/grpc/policy.rs), [official curl artifacts](https://github.com/curl/curl-container), [native musl loader](https://git.musl-libc.org/cgit/musl/plain/ldso/dynlink.c), [pinned Kubernetes API](https://github.com/kubernetes/api/blob/v0.35.8/networking/v1/types.go), [native default-deny egress semantics](https://kubernetes.io/docs/concepts/services-networking/network-policies/#default-deny-all-egress-traffic).
