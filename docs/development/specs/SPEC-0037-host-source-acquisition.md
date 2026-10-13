---
id: SPEC-0037
kind: spec
title: Host acquisition of exact benchmark commits
status: draft
updated: 2026-10-13
related: [SPEC-0012, SPEC-0025, PLAN-0021, PLAN-0041, ISSUE-0006]
---

# Host acquisition of exact benchmark commits

## Goal and scope

Every real benchmark case needs its repository at an exact commit on the host before anything else can happen: [SPEC-0012](SPEC-0012-immutable-source-artifacts.md) `GitSource` captures the authoritative `SourceSnapshot` only from a complete private bare repository, and the [SPEC-0025](SPEC-0025-sandbox-source-fetch.md) sandbox fetch admits its checkout only against that snapshot. Until now nothing fetched; the JSPWiki repository was fetched by hand under [PLAN-0021](../plans/PLAN-0021-multilingual-corpus-admission.md). This spec adds the missing host step: fetch one exact commit over HTTPS from a public host into a new private bare repository, prove the commit is the one requested, and measure it. It also covers resolving each of the 50 inventory cases (`benchmarks/candidate-cases.json`) to a repository and fix commit, and records the result per case in `benchmarks/source-pins.json`.

Excluded: private repositories (no host credential path exists; [SPEC-0025](SPEC-0025-sandbox-source-fetch.md) puts the private token in the trusted worker, not designed yet), submodule contents, Git LFS, checkout, builds, and any claim that a fix commit's parent is the vulnerable revision. Sandbox fetch and storage limits remain separate gates.

## Boundaries and design

**Adapter** `corsair.adapters.git_acquire.GitAcquisition`, beside `GitSource` and reusing its pinned `Executable`, receipt directory and Git object hashing, and the SPEC-0025 `FetchTarget` as input. One call: `acquire(FetchTarget, destination, operation)`.

- **Transport is operator-owned.** `HostTransport` names allowed hosts and, explicitly, any proxy and CA bundle. The child environment is rebuilt as in `GitSource`: no inherited `GIT_*`, credentials, helpers, proxies or global/system configuration; `protocol.allow=never` with only `https` re-enabled for the fetch call; `credential.helper` empty; hooks disabled; `transfer.fsckObjects=true`. A `FetchTarget` with a credential binding is refused before dispatch. No TLS bypass.
- **Fetch.** A new destination is created exclusively (mode 0700, never reused), initialised bare without templates, then `git fetch --no-tags <url> <commit>:refs/corsair/pinned`. GitHub serves reachable commits by SHA, including pull-request commits. Default depth is none: the complete ancestry of that commit, which is what `GitSource` admits. An explicit depth gives a shallow repository that is recorded as such and is measure-only (`GitSource` refuses shallow input by design).
- **Verification.** The pinned ref resolves to the requested commit; the commit object's Git hash is recomputed from its bytes; shallowness matches the requested depth; `git fsck --strict` passes from the commit. The commit's parents are read from the object.
- **Measurement** (`TreeStats`, from `ls-tree -r -l`): entries, regular files and bytes, largest file, executables, symlinks, submodules and paths that `confined_path` would refuse, for the commit and, when fetched, its first parent; repository bytes on disk; elapsed time and Git version. These size the [SPEC-0025](SPEC-0025-sandbox-source-fetch.md) storage bound and show which cases exceed the capture ceilings, without running either.
- **Bounds.** `AcquireLimits`: wall time (whole process session killed at the deadline), address space and a file-size limit equal to the repository byte budget (`prlimit --fsize`, which kills Git's pack writer with `SIGXFSZ`), then the total on-disk size is checked. All are operator ceilings.
- **Typed step.** `AcquiredSource.target(commit)` returns the `FetchTarget` for the acquired commit or its fetched first parent, which is what the composition hands to the SPEC-0025 sandbox fetch after `GitSource` captures the same commit from `repository`.

**Failure layers** (`AcquisitionError.layer`, with an intent/result receipt carrying every native call's arguments, exit, time and stderr tail): `configuration` (refused before dispatch), `host_network` (proxy refusal, DNS, connect, TLS), `source_unavailable` (host says the commit or repository is not there), `transport` (any other fetch failure), `budget` (wall, file size or repository bytes), `source_admission` (wrong commit, digest, shallowness or fsck), `native_git` (local Git failure). Classification of fetch stderr is pattern-based; the raw stderr is always kept. A failed or unknown fetch is not repaired or retried in place.

**Case resolution** (`evals/benchmark/sources.py`, offline): a case resolves when its fix reference is a commit URL (`…/commit/<sha>`, `….patch`, GitLab `/-/commit/`) or a GitHub pull-request commit URL; the fetch URL is the repository named in that reference, and a mismatch with the inventory's `repository_url` is recorded rather than corrected. Rows without a fix reference are listed as unresolved with the reason. The script reads the inventory directly so it does not depend on the case loader proposed separately for IDEA-0005 step 1; it can switch to that loader once both are merged. The first parent is recorded as `baseline_candidate` only when the fix has exactly one parent.

Alternatives considered: shallow `--depth=2` by default (smaller, but `GitSource` refuses it and SPEC-0012 is qualified on complete repositories; kept as an explicit measure-only option); `git clone --mirror` (fetches every branch and tag, unbounded by the case); GitHub archive tarballs (no Git object identity to verify, and no ancestry).

## Acceptance and validation

Offline (local Git, the network fetch replaced by a pinned wrapper serving a local origin): complete acquisition verifies and measures, the receipt records the network call, and the unchanged `GitSource` admits the fetched parent; explicit depth is shallow and has no parent stats; proxy refusal, missing commit and other fetch errors map to their layers with stderr retained; the wall deadline kills the fetch; a server answering with another commit is refused at `source_admission`; the repository byte budget stops the pack writer; a foreign host, a credential binding or an existing destination dispatch nothing; tree parsing counts non-canonical paths and refuses unknown entries; every inventory row resolves or names its gap; the committed pins agree with the resolver.

Network evidence: one run of every resolved case from a cloud container through its egress proxy, results in `benchmarks/source-pins.json`, receipts under `.runs/` (ignored). That run is host acquisition evidence only; it does not qualify the sandbox fetch, storage, any build or any case.

## Decisions and open questions

Coordinator brief on 2026-10-13, under the user's instruction to continue until every benchmark can be tested: host-side fetch and pinning for all cases with a commit, public repositories only, shallow where the host allows. Shallow was not made the default because the existing authoritative capture refuses it; a full-ancestry repository is the input SPEC-0012 already qualified. Open: cases whose repository or capture exceeds the bounds need either larger operator ceilings or the repository-scale source work (IDEA-0005 G2b) before they can be captured; private repositories need a host credential design. Plan: [PLAN-0041](../plans/PLAN-0041-host-source-acquisition.md).
