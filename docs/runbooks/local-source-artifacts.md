# Local source and immutable artifacts

This is the independently qualified local-host boundary in [the report](../qualification/local-source-artifacts.md). It does not admit native OpenShell transfers; [ISSUE-0006](../development/issues/ISSUE-0006-native-transfer-retry-admission.md) blocks that component. No gateway is needed for these host checks, and none is created.

Operator configuration supplies an absolute private user-owned0700 object root and separate0700 receipt root, complete trusted private bare repository, exact40-character SHA1 commit, UUID operation, immutable executable SHA256 identities and SourceLimits. Roots must never be workload mounts; repository configuration/alternates and executable ancestry are operator-owned. Use LocalArtifacts.put(bytes, expected_sha256=...) and digest-checked get(ArtifactRef). GitSource captures committed bytes through native fsck/ls-tree/cat-file, without checkout/archive/filter/hooks/remote acquisition. Keep result references/journals outside workload reach. Unsupported types/paths and exceeded budgets fail admission; do not lower checks to make a repository pass.

The native Git command budget supervises pipe output and child lifetime. Local filesystem writes/fsync remain synchronous and have no hard I/O deadline; disk stalls/power-loss recovery are unqualified. Host commands run under supported prlimit AS512MiB/CPU10s. No custom helper, credential forwarding or sandbox file protocol is supplied. Raw native stderr stays in private receipts. Missing resource telemetry is unknown.

Prepare a new ignored source manifest containing SHA256 of each SOURCES path in tests/qualification/qualify_artifacts.py, with copies of those exact bytes before dispatch. Operator-reviewed configuration JSON has git/prlimit {path,sha256} and limits {max_files:128,max_file_bytes:1048576,max_total_bytes:4194304,wall_seconds:20,memory_bytes:536870912,cpu_seconds:10}. Do not reuse evidence directories or silently compute replacement executable identities after a mismatch.

```shell
UV_OFFLINE=true make test-config
UV_OFFLINE=true make qualify-artifacts \
  CORSAIR_QUAL_RUN=.runs/new-artifacts-001 \
  CORSAIR_ARTIFACT_CONFIG=.runs/operator-prepared/host-config.json \
  CORSAIR_SOURCE_MANIFEST=.runs/operator-prepared/source/manifest.json
```

A separate new process/directory repeats the matrix; qualification.json and protected original operation journals must pass independently against frozen source and actual objects. The fixture builder writes only bounded trusted synthetic Git objects. It checks original fixture-root device/inode before removal; valid objects/receipts remain deliberately retained evidence. Corrupt fixture artifacts are removed only after original-inode confirmation. A failed run never becomes pass by replacing its log/source or repeating an unknown operation identity.

ArtifactStorageError retains reference, publication (including unknown/durability_unknown) and exact temporary name/original identity/cleanup. SourceCaptureError retains native calls, partial admitted artifacts, known snapshot and receipt-storage failure. Intent without authoritative result requires reconciliation, not blind replay. A valid completed snapshot with result-storage failure stays available in the exception. Same immutable byte identity may be read/validated; digest mismatches must not overwrite existing objects. Never sweep an unexpected/replaced partial file automatically. Operator retention is separate from fixture cleanup; no garbage collector is implemented.

Before native transfer work, resolve the supported retry/extraction resource gap and then perform actual current-node storage/kernel/CNI/gateway controls and original-ID cleanup. Keep TLS/policy/pins/kernel requirements intact. This host record cannot substitute for those gates or qualify remote concurrency, disk faults, writer interruption, agents or Temporal.
