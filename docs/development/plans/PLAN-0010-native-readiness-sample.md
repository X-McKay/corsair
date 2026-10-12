---
id: PLAN-0010
kind: plan
title: Native readiness sample
status: complete
updated: 2026-10-11
related: [ISSUE-0004, SPEC-0008, PLAN-0009]
---

# Native readiness sample

## Objective and dependencies

Characterize a small fresh-node sample using pinned OpenShell v0.1.3 SandboxClient.wait_ready's actual 300-second default. This is an observation budget, not an SLO. Historical 120-second attempts retain their original interpretation. User authorized this and the subsequent bounded lifecycle adapter. Actual storage/kernel/CNI/gateway admission is mandatory on each fresh node.

## Steps

- [x] Add a sampler reusing qualified native ownership/profile/policy/cleanup helpers; run offline guards and collection first.
- [x] Observe three normal CPU 1/512Mi fixed-image creates on each of two fresh nodes, retaining every attempt and native timings.
- [x] Audit source bindings, native prerequisites and immutable resource/private/cluster cleanup; update ISSUE-0004 and report.
- [x] Review records and append the session handoff.

## Validation and progress

Resume verified branch codex/openshell-lifecycle-adapter, clean base eccb25bd5711e632b17e667f41c326fe01789255, parent draft PR8 and its successful exact-head offline CI 38173114988. 94 baseline guards passed. Historical recovery010/011 raw JUnit, source hashes, all sandbox IDs and cluster/private cleanup re-audited in .runs/lifecycle-adapter-resume/prior-evidence-audit.json. Original ordinary-pod raw is unavailable and is not reconstructed. Latest primary releases remain OpenShell 0.1.3 and Agent Sandbox 1.0.6; Helm 4.3.0 exists, but qualified3.22.0 remains selected. All pins/security unchanged.

Offline collection initially failed before dispatch because direct uv lacked repository UV_CACHE_DIR; corrected explicit environment collected 1/10. An admission command accidentally reused historical .runs/lifecycle-admission-001: empty-directory guard refused all cluster work, but pytest overwrote its historical JUnit with the error report. Original other receipts remain; old JUnit is unavailable, not reconstructed. Error copied to .runs/lifecycle-adapter-resume/admission-directory-collision-junit.xml; use new adapter-prefixed run directories. Added pre-pytest existing-directory guards to admission/network Make targets to prevent this specific loss. Fresh adapter-admission-001 subsequently passed; adapter-admission-002 independently passed.

## Decisions and next action

Use three explicit native repetitions per node and no retries. Record native create/wait timing, actual Ready identity and cleanup; internal poll/RPC counts remain unknown. Reuse the fixed qualified Python image and existing recovery ownership helper. Both fresh samples and their prerequisite/cleanup audits passed; ISSUE-0004 is resolved for this observation. Adapter integration began only after the first native sample and fixture cleanup passed. Both nodes qualified the separately recorded adapter slice after explicit gateway reinstall; sample runtime inputs remain unchanged. After node 1 sampling, the ownership helper gained an optional operator name for the adapter harness; its default native sampler path is unchanged. Preserve each run’s distinct helper hash rather than claim byte-identical sample sources.

Final acceptance: both independent fresh-node runs audited against raw receipts and frozen sources; all original resource, namespace/PV/private/forward and cluster IDs confirmed absent. See the reviewed [readiness](../../qualification/openshell-readiness.md) and [adapter](../../qualification/openshell-adapter-lifecycle.md) records. Final offline/diff review, HANDOFF-0013 and tracked stacked-draft publication are the closing session steps; remote exact-head CI is verified after publishing, not claimed as live runtime proof. No execution/transfers/agent/durable work was started.
