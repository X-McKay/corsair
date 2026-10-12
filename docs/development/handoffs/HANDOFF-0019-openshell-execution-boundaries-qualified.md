---
id: HANDOFF-0019
kind: handoff
title: Native 1F and execution boundaries qualified
status: recorded
updated: 2026-10-11
related: [SPEC-0008, PLAN-0009, SPEC-0010, PLAN-0012, PLAN-0013, ISSUE-0006, PLAN-0014]
---

# Native 1F and execution boundaries qualified

## Verified state

Prepublication branch codex/openshell-remaining-qualification, clean starting base5ea23a5ac04d6c2a1da0338a65e5078cae098c9b. Open draft parent PR12/head and successful exact-head CI38185303245/148 checks verified before edits and parent rechecked unchanged before publication. This document is committed with tracked qualification cases/records; resolve its published revision/PR/CI using git and native GitHub data, not a future invented SHA. Root owns runtime/edits/publication; three user-authorized sub-agents independently audited recovery, native download admission and composition/fault cases. No unrelated changes were present or overwritten.

[Corrected native1F](../../qualification/openshell-recovery.md) passed recovery-default-host-001/002:1pass226.369/250.549s, on fresh UIDs3c20846d-043c-4c05-8996-7152da4dacde and29cb72d6-13dd-4b4a-bae2-ff978c894b36. Both actual storage/kernel admissions and three CNI controls passed before native gateway/workload dispatch. Four cases per node include matching original sleeping process/start ticks/no finished marker, post-restart original PVC/PV continuity and native OOMKilled137. Native readiness uses the supported default300s without an SLO; historical120-second failures/source and unknown outcomes are preserved. Native source-v2 manifest binds67 inputs and both direct source receipts.

[Existing execution boundaries](../../qualification/openshell-adapter-execution.md) passed execution-artifacts-host-001/0021pass95.939/94.899s and execution-receipts-host-001/0021pass136.142/135.108s. Completed exact1024B stdout/23B stderr enters immutable host artifacts and survives a fresh host reader after original sandbox cleanup. Real original SDK Process loss retains unknown delivery/completion without replay, with independent remote process continuity; actual result-storage EACCES preserves successful native terminal0/exact88B output in memory but no authoritative result. application-source-v3 binds68 inputs; adapters/ports, pins, TLS, policy, kernel and budgets are unchanged. Six application workers reaped, application attempts6/retries0;68 helper SDK records (62ack plus6 expected post-delete NOT_FOUND),12 worker SDK attempts,12 observer execs,464 native commands and2446 retained output bytes. Missing worker-loss RSS/internal RPC telemetry remain unknown. Fresh receipt-reader crash/recovery is not qualified by parent intent/result inspection.

## Validation and blockers

Pre-live and closing UV_OFFLINE=true make test-config passed148 checks (closing4.56s); all15 live tests collect offline without dispatch (0.05s) and git diff --check passes; actual dedicated marker collection/fixture discovery passed before each new case. Completed JUnit and independent frozen-source/native-output/fault/policy/resource/cleanup audits pass all six matrices. Final aggregate reconciles14 unique original sandbox IDs across two nodes. Raw audits/metrics and every preparation failure are retained under ignored .runs/remaining-qualification and per-case evidence roots; no raw/private evidence is published.

Preserved preparation failures include reader/import/cache paths, unavailable pidfd APIs in the selected Python3.12.13 build, and audit snapshot/nullable-result/expected typed post-delete absence assumptions. The supported unique original multiprocessing Process API already used by supervision passed an actual bounded local kill/reap preflight; it is restricted to an exclusive parent and is not atomic expected-start signalling. No extra kernel requirement, raw-PID fallback, retry or bespoke runtime was introduced. Actual EACCES is a host persistence failure, while production retains reason=terminal/failure_layer=null plus storage_error. It is not a native workload failure.

Every original sandbox CR/pod/PVC/PV/task, gateway namespace/PV/private/forward identity is absent. Final fixture inventories are empty. Original cluster CIDs61b9b0028f21f8e11305edde37411866401ff9164b52ac2ef707969cc9eba173 and fd5fdf83bf988140d6c0ebd490ec43294946c305b9308c20ef5d14b1d73c9749 were identity-checked before native deletion and independently absent afterward. No live installation/private state remains. Valid host output artifact objects are intentionally retained private evidence. Older missing ordinary-pod raw exports remain unavailable; current fresh exact-node native prerequisites supply actual new evidence rather than reconstructing history.

[ISSUE-0006](../issues/ISSUE-0006-native-transfer-retry-admission.md) and PLAN-0013 remain blocked for untrusted extraction/application transfer recovery. Fresh primary release/source/help review keeps the admitted OpenShell0.1.3/Agent Sandbox1.0.6/Helm3.22.0 tuple (latest Helm4.3.0 not adopted). Native download extracts all archive members before completion/type/placement checks, with no aggregate-byte/member/inode quota or exactly-one-entry admission, and fixed four whole-operation attempts. Context7 is discovery; immutable pinned primary source decides behavior. No supported admission/reconciliation solution was found. Controlled native upload remains separately qualified. Source staging, controller/transport/storage-durability faults, cancellation, journal attacks, concurrency, full Milestone2, PydanticAI/Temporal and production reliability remain unqualified.

## Decisions and next steps

Keep native features first and the current small unchanged adapters. Direct bounded stdout/stderr storage needs no file transfer. Do not resume the withdrawn Docker staging experiment, add a transfer/repair runtime, weaken gates, or treat intent without result as replay permission. Next bounded action: review the concrete source-upload consumer and writer/concurrency assumptions against the existing native-upload qualification, then define only a demonstrably supported narrow consumer contract. Untrusted file ingestion remains blocked until enforceable native admission or a specifically reviewed narrower contract actually resolves ISSUE-0006.

Existing authorization permits tracked stacked draft publication above open PR12 and exact-head CI verification. It does not authorize merge, deployment, external issue closure or messages upstream. Root reviews the final tracked diff and closing offline records before committing; publication/CI are verified after this prepublication snapshot. Never commit .runs/, .state/, credentials or raw logs.

## Continuation prompt

```text
Read AGENTS.md, README.md and docs/development/CURRENT.md; use Corsair development/review/handoff skills. Read PLAN-0013/ISSUE-0006, PLAN-0012 and this handoff. Inspect branch/git status/source, actual published PR/head/CI and current primary upstream releases. Verify raw two-node native1F/output/fault/source/cleanup records rather than trusting this handoff. Work only on the concrete native source-upload consumer/writer admission review; retain supported immutable artifacts and existing gates. Untrusted file download, application retry/reconciliation and dependent integration stay blocked unless actual enforceable admission resolves the issue. No new transfer runtime, generic repair loop, policy/TLS/pin/kernel weakening, PydanticAI or Temporal. Run smallest relevant offline checks before any authorized live work, freeze input/source bytes, preserve every failed/unknown attempt and original-ID cleanup, update work records/CURRENT, review the diff and append a new handoff. Publish only authorized tracked changes; never raw run/state/credentials.
```
