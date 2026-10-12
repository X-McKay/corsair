---
id: ISSUE-0005
kind: issue
title: Execution worker native resource admission
status: resolved
updated: 2026-10-11
related: [SPEC-0010, PLAN-0012]
---

# Execution worker native resource admission

## Observed and expected behavior

Fresh execution-host-001a reached native create/Ready and control, then the first real execution adapter operation hit its host deadline without output/terminal acknowledgement. Expected bounded binary control completion. The exact worker was reaped with -9; delivery/completion remain unknown. This is host worker/native-client admission failure, not workload-policy denial or an application assertion. Native 1A admission passed; it does not qualify this new host worker profile.

## Reproduction and evidence

Raw source-v3, JUnit (1 failed/248.24s), native SDK/lifecycle/identity/cleanup and worker receipt retained under .runs/execution-host-001a and .runs/execution-adapter-resume. Original sandbox 57b29f55-b9f4-4e09-8337-abed47d26c82, operation 401988bc-e9d7-482b-973b-7dc1532b6844, worker PID3365396: get/exec_stream attempts, hard RLIMIT_AS536870912 confirmed, no terminal output, host timeout21.023s with cleanup grace. Captured native stderr reports pthread_create failed, Resource temporarily unavailable. Full original CR/pod/PVC/PV/container-task and gateway namespace/private/forward cleanup confirmed; cluster deletion is separately checked.

## Attempts and diagnosis

Bounded local no-credential SDK probes on the actual host reproduce native thread-allocation errors at 512MiB and 1GiB under unrestricted 32-CPU affinity; VmSize approaches the respective hard cap while RSS remains about45MiB. A one-CPU affinity probe at the unchanged 512MiB cap reaches expected closed-local-port UNAVAILABLE without thread-allocation diagnostics (VmPeak487540KiB,19threads). Sandboxed probes also retained but their socket denial is not native network qualification. Exact probe children reaped. This supports a host native allocation/scaling interaction; detailed library/allocator root cause is not proven. No SDK pin, policy, TLS, kernel requirement or memory/output/deadline limit changed.

Add supported Linux single-CPU worker affinity before native channel creation, retain the memory ceiling and output/deadline budgets, expose observed affinity and unknown missing limit telemetry. Source-v4 must be frozen and admitted with actual controls on two fresh nodes; no replay of the unknown original operation. Original operation outcome remains unknown after cleanup.

## Resolution criteria and next action

Require the unchanged-budget real binary/nonzero/timeout/continuous-output/refusal matrix to pass on two fresh mandatory-admitted nodes with actual worker hard-limit/affinity receipts and full original-resource/fixture/cluster cleanup. Keep the earlier failed operation unknown and excluded. Do not resolve from offline probes, larger limits, version strings or a retry on the original handle.

Single-CPU source-v4 execution-host-002 passed a complete matrix, but execution-host-003 failed its third binary control with identical pthread_create diagnostics and unknown operation c2b1e112-3b23-42fd-ab5d-b8d2e5f3a7a4 (worker 3496845). All three original sandboxes/resources and complete fixture cleanup confirmed; this profile fails two-node acceptance. Keep the first pass as an intermediate observation, excluded from final source-v5 qualification.

GNU glibc 2.39 documents process-local mallopt(M_ARENA_MAX,2); installed malloc.h confirms parameter-8. Five actual-host no-credential probes with this profile, one CPU and unchanged 512MiB AS limit had no native thread errors, observed channel VmSize290160KiB, and all exact children reaped. These are diagnostic probes, not OpenShell qualification. Source-v5 explicitly admits only glibc 2.39, calls the supported allocator API in a single-threaded spawned worker before channel creation, retains all caps, and records libc/arena acceptance. No system/library/environment patch or larger budget. Require two new fresh-node matrices before resolution.

Resolution: final source-v6 execution-host-004/005 passed complete three-cycle matrices on distinct fresh node UIDs 26fcdced-ede4-47cb-ab6c-3121f18c636b and b84127f9-e300-437e-9aba-21f762b108c2 (208.799/217.826s). All 30 workers reaped; all 24 active executions reported the unchanged hard AS/CPU and glibc 2.39/two-arena profile. Actual binary0/nonzero7/native 124 / continuous overflow/forged-ID controls passed six times each. Both raw/source/identity audits and complete original-resource/fixture/cluster cleanup passed. Criteria resolved for this bounded profile only; the two earlier operations remain unknown, detailed upstream cause/fleet reliability unproven. See the [reviewed qualification report](../../qualification/openshell-adapter-execution.md).
