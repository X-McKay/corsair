---
id: SPEC-0012
kind: spec
title: Immutable local source and artifacts
status: accepted
updated: 2026-10-13
related: [PLAN-0014, SPEC-0011, SPEC-0037]
---

# Immutable local source and artifacts

## Goal and scope

Implement the independent local artifact/source storage slice of Milestone2 over [execution/recovery](../../execution-and-recovery.md). Preserve exact bytes with SHA256 references, atomic no-overwrite admission, digest-checked reread after process restart and an immutable source manifest for an exact local Git SHA1 commit. No remote fetch, checkout, hooks, sandbox mounting/transfers, artifact materialization, agents or Temporal.

## Boundaries and design

Use standard filesystem operations for content-addressed objects and native Git plumbing for raw committed blobs. No generic storage service/archive parser. Operator supplies an absolute private user-owned0700 root, Git/prlimit executable identities, complete trusted bare repository, and fixed resource budgets. The native pipe deadline does not impose a hard filesystem-I/O deadline; disk stalls remain unqualified. Only UTF8 canonical relative POSIX paths and regular modes100644/100755 are admitted; reject symlinks, submodules, special/unsafe/.git paths and duplicate/colliding entries. Ignore worktree dirt, filters and export substitutions by reading committed objects directly; check original Git blob/commit hash and expected SHA256 bytes. Native fsck --strict validates object integrity including trees; native Git protocol access disabled; full offline bare repository is an operator prerequisite.

Objects are fsynced and atomically linked under digest names without overwriting, then directory-fsynced. Existing content must pass size/type/owner/mode/digest validation. Publication failure retains possible admitted identity; orphan temporary objects remain nonauthoritative and cleanup is exact-identity checked. Logical immutability does not prevent the trusted host operator changing bytes; integrity checks detect corruption. One exclusive worker/root only; production concurrency/remote storage/host compromise unqualified.

## Acceptance and validation

Small offline contracts before live host-native qualification: conflict/digest mismatch, corrupt/symlink objects, path/type refusal, bounded source size/count/output/deadline, exact committed bytes despite hooks/filters/worktree changes and retention of partial failure. Qualify real Linux filesystem/Git/prlimit in two independent host processes/roots with source capture, fresh reader restart, no hook marker, raw native command/resource observations, and identity-checked fixture cleanup. Preserve failed attempts. This admits local storage only, never OpenShell transfer or distributed/crash durability.

## Decisions and open questions

User continuation authorizes independent storage when native transfer admission is blocked. No native library already exposes this application-specific artifact/manifest contract; minimal standard storage/digest bookkeeping serves the concrete consumer. Budgets are operator resource controls, not SLOs. Git SHA256 repositories, invalid UTF8 paths, partial clones, source checkout/materialization, storage power-loss/concurrency and remote backend remain unsupported/unqualified.

2026-10-13: [SPEC-0037](SPEC-0037-host-source-acquisition.md) extends `GitSource` with two default-off operator options (ignore three format-only fsck message ids; skip and list symlinks and submodule links) and raises the source ceilings for real benchmark trees. The original qualification covers the default path at the original ceilings only; the new options and ceilings have offline tests and benchmark capture evidence, not a renewed qualification run.
