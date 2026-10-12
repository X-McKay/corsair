# OpenShell captured-source arrival qualification

Date: 2026-10-11. **The fixed pre-execution source-arrival composition passed on two fresh admitted nodes, with confirmed original cluster cleanup.** This is [SPEC-0011](../development/specs/SPEC-0011-native-transfer-admission.md)'s five-file consumer fixture under [PLAN-0013](../development/plans/PLAN-0013-native-transfer-admission.md). It adds no application transfer API, repository execution or general materializer. [ISSUE-0006](../development/issues/ISSUE-0006-native-transfer-retry-admission.md) remains blocked for broader transfer admission.

## Native composition and authority

[The case](../../tests/qualification/test_source_upload.py) reuses GitSource, LocalArtifacts, protected receipts and existing native gateway/ownership fixtures. Native offline Git captures an exact complete private bare repository without checkout, hooks, filters or export substitution. Successful capture is bound to a digest-checked manifest and five independently reread blobs. Constructing a SourceSnapshot dataclass alone is not admission.

The fixture contains raw attributes, a 1 MiB binary, an empty file, quoted/Unicode paths and an executable-bit entry. Total source bytes are 1,048,661. Separate private host staging files map Git100644 to0400 and Git100755 to0500; directories are0700. These are staging permissions preserving executable meaning, not exact Git worktree permissions. Authoritative artifact objects stay0400 and are never chmodded. Every staging entry's type/owner/link count/device/inode/size/mtime/digest and the immediate private parent's identity are retained and checked after native upload. Host ancestors outside that private root remain trusted operator prerequisites.

The supported command runs once in an operator-exclusive workspace against a fresh owned idle Python sandbox:

```shell
openshell sandbox upload --no-git-ignore NAME PRIVATE_UUID_DIRECTORY /tmp
```

[Pinned native source](https://github.com/NVIDIA/OpenShell/blob/e1f3c82caa3ed3b65de22889ae7ef32a774878ef/crates/openshell-cli/src/ssh.rs) wraps the directory basename and uses tar-over-SSH. It may merge partial writes on up to four native-owned whole-operation attempts. All writers are excluded through preparation and admission; repeating the fixed bytes remains confined to disposable scratch before any repository consumer runs. There is one outer invocation per matrix and no application replay. Lost/failed acknowledgement stays unknown and retires the original sandbox. Host timeout does not prove SSH/proxy descendants stopped; retained staging must not be deleted or reused while their completion is unknown. No interruption or exactly-once claim follows from these successful operations.

A fixed trusted verifier requires original sandbox and /tmp identities, exact root/nested directory inventory, workload ownership, regular files, staging modes, sizes and digests. It reads at most1MiB/file,4MiB total and admits exactly5 files/2 directories with at most4096 output bytes. Two independent complete observations agree. Actual changed bytes produce an assertion refusal; an unexpected symlink produces O_NOFOLLOW/ELOOP refusal. These are pre-execution admission observations, not an application security-fix verdict or hostile arbitrary-tree quota qualification. After native admission, the original artifact root and every authoritative manifest/blob identity and digest are reread unchanged. No hook marker exists and no repository entry point runs.

## Actual evidence and measurements

Frozen source-v1 binds69 inputs: SHA2563a9ebb75e5e407e3dad2ade77c056334bbb147206cd6e9102390ab1388d94d08. Qualification file SHA2567edc48c0dff87fe6193682b27d196322ca5e8cc2a311fd92afc8c6fa34d7a4d8. All current/frozen bytes and direct per-case source receipts match. Native tuple, policy, TLS and kernel requirements are unchanged: OpenShell0.1.3 at e1f3c82, Agent Sandbox1.0.6 and Helm3.22.0. Current primary releases still list OpenShell0.1.3/Agent Sandbox1.0.6; latest Helm4.3.0 was not adopted. Fresh primary source matches ssh.rs SHA25604ec7f978ec01b57c271819a4c078089e838f7df8032f61fc61cf898bedb0e87. Context7 supplied discovery; actual immutable source determined retry/path behavior.

| Matrix | Node UID | Storage/kernel seconds | CNI cases/seconds | Source suite | Capture seconds | Upload seconds | SDK calls | Native commands |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| source-upload-host-001 | 7135ee94-1b8c-4b0b-a603-eec9569e4403 | 89.642 | 3/157.371 | 1 pass/97.080s | 0.030676 | 0.060606 | 16 | 108 |
| source-upload-host-002 | b73eb51f-0198-4a79-a961-a489e9a63fdb | 93.551 | 3/156.955 | 1 pass/95.115s | 0.029310 | 0.060736 | 16 | 107 |

Both exact nodes passed actual storage remount/kernel probes and CNI allow/deny/rollback before native gateway/workload dispatch. Native readiness retains its supported default300s; observed latencies are not SLOs. Each capture has16 reaped Git/prlimit children, including one expected absent-config exit1. Git SHA2562a8c18fbf43da9f692d75474c72bea9dfd796c260b0f3dfe456376abc3bbd668 and prlimit SHA25617064f67e650d6152a6902b013aab496b54c87587c8eea6f5023aafee6154069 match the existing host-native qualification.

The identical fixture commit is40612c675a42e735ce9537374089ca06f93e3350, treecc45b70c151b7b109ccc4cc41d512a211297480b and1122-byte manifest SHA256abf1ab120d171d3d81e365f8d77294d5cb50f7a57acee5bfcf0bacb5f69d2ffa. Independent loose Git object decoding verifies commit/tree/blob SHA1 and exact stored SHA256 bytes on both nodes. Combined measurements:32 reaped source calls,32 acknowledged helper SDK records/16 execs,215 native commands,4374 retained SDK output bytes and two outer uploads/application retries0. Internal native attempts/RPC counts and peak RSS remain unknown. No agent/model/provider calls occur.

Private evidence remains under ignored .runs/source-upload-consumer-review and the named matrix/admission/network roots. Root's source-two-node-raw-audit.log and source-raw-audit-2.json require actual JUnit, native receipts, manifest/objects, refusal cases and original resource/task/namespace cleanup. Independent source-composition-independent-001-002.json under .runs/remaining-qualification/recovery-review additionally decodes Git objects and compares both full snapshots. No summary-only pass is counted.

Original source sandbox IDs24438c41-0682-4377-a8cc-e7684da16867 andfda070f7-9b3f-4ce7-9c41-93619d54de9d have confirmed CR/pod/PVC/PV and container-task absence. Gateway namespaces/PVs/private state and original owned forwards are confirmed absent. Final sandbox/PV inventories are empty. Exact original cluster CIDs5af4f5e820a72fee7f86eaeb3bf292eaa8e671391bb559996d61669e5d0ea10c and2b7ce23ed1d3fe87af5d4720318aa197f9db887a280ade0a45ea4191eab56dae were checked before native deletion and independently absent afterward. Both private kind owners/kubeconfig and active OpenShell state are absent. Host staging, source repositories, artifacts and receipts are intentionally retained private evidence.

Pre-live148 offline checks, actual selected1/16 collection and local bounded verifier positive/corruption/symlink preflights passed. Initial missing src import failed before fixture creation; historical-source audit initially compared today's marker registration to old inputs before being corrected to published72e blobs; independent audit initially used a wrong Docker argv index. Every failed preparation is retained, without modifying the raw runs. Independent review corrected cleanup/outcome attribution, host parent/object identity reread and /tmp ownership before freezing. Both actual live source matrices passed; no failed live source attempt is discarded or relabelled. Closing offline/diff/publication results are recorded in PLAN-0013 and the next handoff.

## Remaining boundary and next step

Read-only files inside owner-writable directories do not make source immutable while code runs. A workload can chmod, unlink or replace its own entries; pre/post digests do not freeze intervening writers. Native Landlock grants are additive, so a read-only child cannot remove a writable ancestor or include_workdir grant. Those facts limit claims about the staged copy; authoritative host snapshots/artifacts remain separate.

The [execution contract](../execution-and-recovery.md) explicitly permits an admitted staging copy and states that integrity checks do not detect every transient modification. The next bounded step is native staging-copy-to-execution input binding using existing execution/output-artifact components: freeze source/test/recipe, restrict patches to approved test paths, verify relevant bytes before/after execution, invalidate observed production-source changes, retain actual command/output receipts and preserve unknown delivery. Source arrival alone does not qualify that consumer.

Final contract review withdrew a proposed mandatory root-owned source-image/read-only-PVC gate as stronger than the accepted staging contract. Stronger sealed-source media can be reviewed later if a concrete consumer requires that guarantee. No new image or driver/PVC profile is adopted here; the standard native upload path remains the selected arrival operation.

General source materialization/API, source execution, active/concurrent workspace uploads, interrupted transfer/host descendants, cancellation/reconciliation, untrusted downloads, controller/transport/storage durability, agents/Temporal and production reliability remain unqualified. The withdrawn Docker staging experiment remains withdrawn. This result advances source arrival without changing ISSUE-0006's broader blocked criteria.

## Qualified fixed execution follow-up

The subsequent [fixed staging-source execution/output composition](openshell-source-execution.md) passed on two fresh admitted nodes with full original cleanup. This advances only a five-file stdlib fixture with an empty approved test-patch set, exact input/runtime/policy binding, post-execution source observations and immutable bounded outputs. General recipes/patches, transient integrity, untrusted files and transfer reconciliation remain unqualified; the arrival evidence above retains its original scope.
