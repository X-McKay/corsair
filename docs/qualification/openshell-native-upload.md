# OpenShell native single-file upload qualification

Date: 2026-10-11. **Controlled native single-file upload passed on two fresh admitted clusters with confirmed cleanup.** This qualifies only one documented trusted native operation, under [SPEC-0011](../development/specs/SPEC-0011-native-transfer-admission.md) and [PLAN-0013](../development/plans/PLAN-0013-native-transfer-admission.md). Full application transfer admission remains blocked by [ISSUE-0006](../development/issues/ISSUE-0006-native-transfer-retry-admission.md).

## Native operation and limits

The operator supplies one exclusive regular host file, mode 0400, exactly 1 MiB, containing every byte value including NUL and invalid UTF-8. Its original device/inode/size/mtime and SHA256 are checked before and after upload. Destination is a new explicit random /tmp basename in a fresh owned idle Python sandbox, with 512 MiB/1 CPU and the unchanged hard Landlock/no-egress policy. No repository code, concurrent actor or downstream consumer runs there.

[Qualification case](../../tests/qualification/test_native_upload.py) invokes the installed native CLI once:

```shell
openshell sandbox upload --no-git-ignore NAME SOURCE /tmp/OPERATION.bin
```

Existing fixtures admit this exact node's storage/kernel/CNI, then gateway TLS, authentication, identity and CNI controls. Existing native SDK observations require the original sandbox ID and /tmp directory identity, regular file/type/link checks and two identical independent reads matching expected size/hash. A deliberate fixture mutation must change the observed digest. This is an integrity observation, not an implemented application rejection mechanism or a concurrent-race guarantee. Protected exclusive fsynced intent/result receipts remain on the host. Existing original-ID teardown proves API/resource/storage/container-task absence; gateway teardown proves private state and port forwards absent.

The CLI owns up to four whole-operation attempts with 2s delay in the [pinned implementation](https://github.com/NVIDIA/OpenShell/blob/e1f3c82caa3ed3b65de22889ae7ef32a774878ef/crates/openshell-cli/src/ssh.rs). Application retries are zero. Failure or lost acknowledgement stays unknown, with no outer replay; retire the original sandbox. Repeated native writes here remain confined to disposable trusted scratch and cannot publish an authoritative artifact. Internal attempt/RPC counts remain unknown. No exactly-once, atomic replacement, forced-loss recovery, cancellation or arbitrary concurrency claim is made.

The [pinned example](https://github.com/NVIDIA/OpenShell/blob/e1f3c82caa3ed3b65de22889ae7ef32a774878ef/examples/sync-files.md) documents this single-file command. Its transport paragraph describes a streaming implementation that conflicts with the actual tar-over-SSH source; source and installed help determine behavior. Context7 was used for discovery only. Primary source bytes and current releases were checked before editing: OpenShell0.1.3 and Agent Sandbox1.0.6 remain current; latest Helm4.3.0 does not change the qualified Helm3.22.0 tuple.

No host download/extraction, application transfer adapter, source materialization, new runner, transport, policy, runtime pin or kernel relaxation is included. The 1 MiB selection is the existing source-file envelope, not a performance SLO or native resource quota. Fresh nodes always repeat mandatory admission. Full corrected 1F, live transfer faults, untrusted downloads and application/agent/Temporal integration remain unqualified.

## Actual evidence

Private raw receipts and logs stay under ignored .runs/native-upload-resume and the named matrix directories. Frozen source-v2 covers 66 source/input files, including the new case and existing fixtures/runtime inputs. Each upload matrix also captures its direct source hashes. matrix-audit.json independently verified equality with frozen files, actual raw JUnit/CLI/SDK/digest/cleanup observations, distinct node/cluster identities and final resource inventories. closing-container-audit.json independently confirms both original cluster CIDs and the dedicated cluster name absent. Private ownership, kubeconfig and OpenShell state are absent.

| Matrix | Node UID | Original upload sandbox ID | Upload seconds | SDK method calls | Outcome |
| --- | --- | --- | --- | --- | --- |
| native-upload-host-002 | e8f4f126-a304-4c2a-bfc3-ef0039a85100 | 622ec8a6-15ab-4054-8f31-e33cdb2e56e5 | 0.096 | 15 | Passed 1 case/121.49s, fixture cleanup confirmed |
| native-upload-host-003 | aff6b466-6cc3-48a3-b06e-0f586db1dd45 | e47c2a59-2597-4144-8752-5ccb6de46513 | 0.098 | 15 | Passed 1 case/94.93s, fixture cleanup confirmed |

Payload SHA256: fbbab289f7f94b25736c58be46a994c441fd02552cc6022352e3d86d2fab7c83. Each counted run must use one outer upload invocation, unchanged host source, expected destination hash, different corruption hash and original identity/resource cleanup. Timings include native behavior; missing internal telemetry is unknown. No agent/model calls occur.

| Frozen input | SHA256 |
| --- | --- |
| tests/qualification/test_native_upload.py | 9a6dbf45b0a8c40888b0cf0c9769becd35bc638538081e5fb7872d12eed57894 |
| deploy/runtime-lock.yaml | a3b53531f8d7331185c76396a1bcc76163c644f21d9bfa80b3da2feec6a1dac2 |
| policies/openshell/identity.yaml | f586277b32e9b2cfa457f474113e7e16523c48bf8d55d96f8be0df95766d0afc |

First prerequisite matrix: native-upload-admission-001 passed storage/kernel with original namespace/PV cleanup; native-upload-network-001 passed 3 actual allow/deny/rollback cases with fixture cleanup. Original first cluster CID 64c9ef2a44ad68344c5365980e46f221ce31b4ac285876e76b5406d842dc9ede was identity-checked and deleted before the second cluster creation. Final inventory retained separately.

Second prerequisite matrix: native-upload-admission-002 passed storage/kernel with original namespace/PV cleanup; native-upload-network-002 passed 3 actual allow/deny/rollback cases with fixture cleanup. Original second cluster CID 7f99b6bee25b357f703d162f469f983e42c774b46209b95668866f72cfae286c was identity-checked and deleted after full gateway teardown. Both matrices passed TLS/authentication/identity prerequisites and confirmed original namespace/storage/private/forward cleanup. No live upload failure occurred in the two counted runs.

## Failed attempts and proportionate checks

Before live work, 148 offline checks passed and 1/13 qualification cases collected. The first upload attempt native-upload-host-001 failed fixture setup because the new module omitted the existing gateway fixture import. No upload or gateway test fixture was dispatched; the separately installed gateway remained owned. Collection had not exercised fixture resolution. The failed JUnit/command receipts and source-v1 remain intact. One import correction was followed by 148 passing offline checks, actual gateway fixture discovery and a new source-v2 freeze before native-upload-host-002. No possible side-effect operation was retried.

Read-only preparation included an incorrect guessed source path and an absent guessed admission-summary path, corrected using the actual file inventory. Neither changed runtime state. The withdrawn Docker staging failures and their identity-checked cleanup remain in PLAN-0013/HANDOFF-0017; no such profile is resumed or qualified here.

Final Corsair review found no blocking finding within the controlled native-upload scope. Raw summaries alone are insufficient: passing JUnit, independently observed bytes/identities and confirmed cleanup must agree. Remaining gaps above remain explicit; the broader issue is not resolved by these two successful uploads. Closing offline checks and publication are recorded in PLAN-0013 and the new handoff.

## Repeat procedure

Run make test-config and verify test/fixture discovery first. On a new owned cluster, run kind-up, admission-install, toolchain-images-load, qualify-admission, qualify-network and openshell-install with that node's admission directory. Then:

```shell
make qualify-native-upload CORSAIR_NETWORK_RUN=.runs/NEW-NETWORK CORSAIR_QUAL_RUN=.runs/NEW-UPLOAD
make kind-down
```

Use fresh evidence directories, inspect failures before any new dispatch, retain original identities and confirm all cleanup. A passed version command, installation, test collection or earlier node report cannot replace these live gates.

## Subsequent source composition

The separate [captured-source arrival report](openshell-source-upload.md) records a later five-file GitSource/artifact/native-directory-upload composition passing on two fresh admitted nodes. It qualifies idle pre-execution arrival and actual admission refusals only; this original single-file matrix and its failed preparation remain unchanged. Source immutability during execution, general application transfers, untrusted downloads and interruption/reconciliation remain unqualified.
