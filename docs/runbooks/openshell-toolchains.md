# Native toolchain qualification runbook

Scope: fixed trusted native 1E infrastructure projects on the admitted single-node Linux amd64 tuple. These probes do not verify an application finding or fix. See [SPEC-0007](../development/specs/SPEC-0007-openshell-toolchains.md), [PLAN-0008](../development/plans/PLAN-0008-openshell-toolchains.md) and the [report](../qualification/openshell-toolchains.md).

```shell
UV_OFFLINE=true make test-config
make toolchain-images
make kind-up
make admission-install
make toolchain-images-load
make qualify-admission CORSAIR_QUAL_RUN=.runs/toolchain-admission-NEW
make qualify-network CORSAIR_QUAL_RUN=.runs/toolchain-network-NEW
make openshell-install CORSAIR_ADMISSION_RUN=.runs/toolchain-admission-NEW
make qualify-toolchain CORSAIR_NETWORK_RUN=.runs/toolchain-network-NEW CORSAIR_QUAL_RUN=.runs/toolchain-host-NEW
make kind-down
```

Preparation explicitly pulls immutable official Python/Maven amd64 images. Python wheels have primary SHA256 pins and install offline with require-hashes. Maven uses exact project/plugin versions with native strict upstream checksum verification during trusted preparation, then freezes the resulting artifact as a Docker config/containerd manifest. Its complete JAR/POM SHA256 inventory is retained. Preparation controls execute the real projects as UID10001 with no network, capabilities or privilege escalation and confirm original container-ID removal. These controls do not admit OpenShell.

Artifact preparation refuses an existing cache. Inspect successful receipts rather than silently rebuilding; archive a failed cache under a new ignored path before a separately evidenced correction. Native kind load checks the source hashes, Docker config and containerd manifest chain; fresh clusters must load identical artifact identities. Local aliases use the immutable manifest reference, and actual sandbox imageID must match it.

Each new cluster needs real exact-node storage/kernel/CNI controls. The toolchain invocation includes gateway TLS/auth/identity/access-isolation controls. It uploads only the fixed project files through the native CLI, confirms hashes via SDK execution and retains native receipts/JUnit XML. Offline Python and Java build/test success must have exact test IDs/counts and no skips. Separate intentional syntax, discovery, assertion and offline missing-artifact/native Maven prefix-resolver failures retain their producing layer. They do not establish application safety.

Only after both offline language matrices succeed does native policy replacement admit a hash-checked no-cache six wheel download and exact PyPI missing-package GET. HTTPS interception, client certificate verification and REST enforce remain enabled. A trusted echo fixture and a separate Service at an unserved port distinguish admitted registry transport failure from policy denial. Native client close/read-timeout detail qualifies only with a fresh original-sandbox connection-refused event and matching mediated destination/port; export that event before deletion. No providers or credentials are attached. Policy revisions/effective authority and native upstream details are retained. The cold Python path is reported separately; this does not admit arbitrary package indexes, Maven cold downloads, production repositories or historical projects.

Every attempt gets a new evidence directory. Native uncertain delivery stops dependent work; do not replay a possible side effect. Use original sandbox-ID deletion/wait and immutable CR/pod/PVC/PV absence checks. The invocation also confirms endpoint/gateway namespace/PV/private-state/forward cleanup. Before kind-down, retain an empty owned-resource inventory and original Docker cluster ID. Confirm its absence afterward. Never remove unrelated resources or publish private run/state artifacts. Repeat the full toolchain slice on a second independently created cluster before qualification claims.
