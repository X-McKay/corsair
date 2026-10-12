---
id: HANDOFF-0014
kind: handoff
title: Bounded execution adapter qualified
status: recorded
updated: 2026-10-11
related: [SPEC-0010, PLAN-0012, ISSUE-0005, PLAN-0011]
---

# Bounded execution adapter qualified

## Verified state

Branch codex/openshell-execution-adapter; clean source/base before this session af87dce5b28107918d4fbcdf56628cf6f6082939, parent open draft PR9 at that exact head on codex/openshell-lifecycle-adapter with successful exact-head CI38175736016. This snapshot is written with reviewed source/records before their commit. Resolve the published revision using git log -1 --format=%H -- docs/development/handoffs/HANDOFF-0014-execution-adapter-qualified.md and compare native GitHub head/CI; do not invent a future SHA or infer publication from this file alone.

Bounded synchronous execution/output/failure receipts are implemented and qualified: three complete cycles on each of two new admitted nodes, 30 distinct worker operations. Operator supplies complete mTLS, workspace/owner/workdir and immutable limits. Supported SDK exec_stream runs in a spawned host worker with GNU glibc 2.39, process-local mallopt(M_ARENA_MAX,2) before threads, one CPU and hard 512MiB AS ceiling. Native 2s, host 20s plus up to 2s reaping grace, 4096 combined output bytes. No memory/output/deadline/policy/TLS/pin/kernel requirements weakened; no parent/system allocator/environment patch. Exact binary/native terminal/error/failure-layer data retained; native 74/124, missing terminal, overflow and delivery loss remain unknown. No retries or custom transport/scheduler/credential broker.

Shared protected host journal extracted for the demonstrated execution consumer; all 15 lifecycle contracts and six actual lifecycle cycles re-exercised with original cleanup. Native identity/owner/creation labels and Ready mandatory. Name APIs lack atomic expected-ID operation; require exclusive operator workspace/nonreused names. No transfer/artifact/model/Temporal integration.

## Validation and blockers

123 offline checks passed before final live work: 94 repository guards, 15 lifecycle and 14 execution/supervision cases, including actual Linux/glibc-profile acceptance and excess-allocation rejection. Offline worker-loss/deadline/native/storage cases are contract evidence only. Source-v6 under .runs/execution-adapter-resume is byte-identical to both counted manifests; execution-audit-004/005.json bind raw JUnit, original IDs/policy/image/profile, receipts and resource/fixture cleanup. Parent raw two-node lifecycle evidence was independently re-audited before edits; primary releases checked, runtime tuple retained.

execution-host-004 on node 26fcdced-ede4-47cb-ab6c-3121f18c636b:1passed/208.799s,33 lifecycle/helper method observations and 27 worker get/exec_stream attempts. execution-host-005 on node b84127f9-e300-437e-9aba-21f762b108c2:1passed/217.826s, same counts/source. Each matrix: binary0,nonzero7,native 124,continuous overflow and forged-ID refusal across three original sandboxes. All 30 exact workers exited 0/reaped; all 24 active executions reported actual memory/CPU/libc/arena profile. Native internal RPC/poll/retry counts unknown. Observed peak RSS at terminal/overflow110444–111844KiB; missing/after-event telemetry not zero or inferred.

Retain failures: direct uv home-cache collection and system-Python freeze preparation errors (no live mutation); execution-host-001 fixture-discovery error (six read-only commands, no execution dispatch). Original installation/node/empty inventory identity checked before corrected attempt. Source-v3 execution-host-001a failed first control at host deadline with native pthread_create resource diagnostics; operation 401988bc-e9d7-482b-973b-7dc1532b6844 remains unknown, worker 3365396 reaped. CPU-only source-v4 execution-host-002 passed an intermediate matrix, but execution-host-003 failed third control with repeated diagnostics; operation c2b1e112-3b23-42fd-ab5d-b8d2e5f3a7a4 remains unknown, worker 3496845 reaped. All original sandbox/resource/fixture/cluster cleanup audited, no replay. These profiles are excluded from final acceptance. Source-v5 preserves allocator development; source-v6 adds explicit failure attribution. ISSUE-0005 resolved only by the final two fresh matrices; detailed library/allocator cause and fleet reliability remain unknown.

All five original cluster CIDs, including failed/intermediate nodes, confirmed absent in .runs/execution-adapter-resume/cluster-001…005/audit.json after empty final inventory. Final counted CIDs fe3730f1273d02c81940ef6d1dbfdb50a28f04379ca3a2f8ecfe727088ba3a40 and d0602dcb9ad9a1ebbe65727f115d719db73f2637480ef1fbb9fa10b5f0d8d006 absent. Every original CR/pod/PVC/PV/container task and gateway namespace/PV/private/forward identity cleaned. No live cluster/installation, owner/kubeconfig/private state remains; inert caches retained. Raw logs/private evidence are ignored, never tracked.

Historical native 1A–1F remains at source 4aacc8a and original 120s local readiness budget; full corrected 1F matrix unrun. Separate six-sample native 300s readiness observation and prior ISSUE-0004 resolution remain bounded observations, not a product SLO or fleet/cause guarantee. Prior historical admission JUnit availability loss and unavailable original ordinary-pod raw remain recorded without reconstruction.

## Decisions and next steps

Final Corsair review found no blocking finding for this bounded slice after correcting uncertain worker-start delivery, fixture registration, native allocation admission and failure attribution. Completed ordinary exit is an observation, not application-fix proof. Closing a client/host worker is not remote cancellation proof. Current port does not expose stdin/env, workload credentials or operator budgets to an agent. Publication is a tracked stacked draft above PR9; native exact-head CI is verified after publication as an offline check, never runtime proof. No merge, deployment, external issue closure or messaging authorized.

Next bounded component: supported native transfer/path/type/digest contracts, then immutable artifact/source storage. Inspect pinned CLI upload/download retries and uncertainty before designing wrappers; the curated SDK has no transfer methods. Source capture must not run hooks, must validate types/confinement/digest and preserve immutable evidence. Live controller/worker/storage/transport fault recovery, cancellation, event collection, journal attacks, concurrency/production tenancy remain unqualified. Keep each component's focused plan/offline/live gates; do not begin PydanticAI or Temporal.

## Continuation prompt

Read AGENTS.md, README.md, CURRENT.md, Corsair development/review/handoff skills, SPEC-0010/PLAN-0012/ISSUE-0005 and HANDOFF-0014. Inspect branch/status/source and current primary releases; verify published exact-head CI and the two counted source-v6 execution matrices against raw identity/cleanup evidence, including failed/intermediate history. No live installation remains. Proceed only with the next bounded native transfer/path/type/digest slice and its focused plan, then immutable artifact/source storage separately. Inspect supported CLI retry/error behavior; never blindly replay unknown uploads or downloads. Run smallest relevant offline checks before live native work; use unique evidence directories, mandatory current-node storage/kernel/CNI/gateway admission, immutable policy/TLS/artifacts and identity-checked cleanup. Preserve all failures, update reviewed qualification/work records, review final diff, append a new handoff and publish only tracked authorized changes. Never commit .runs/.state/credentials/raw logs. Agents and Temporal remain unqualified.
