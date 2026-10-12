---
id: PLAN-0003
kind: plan
title: OpenShell installation and runtime admission
status: complete
updated: 2026-10-11
related: [SPEC-0003, PLAN-0001, HANDOFF-0004, HANDOFF-0005]
---

# OpenShell installation and runtime admission

## Objective and dependencies

Implement [SPEC-0003](../specs/SPEC-0003-openshell-admission.md), bounded to the remaining 1A prerequisites, storage and native kernel admission. Base/source revision: 1affbba9fc80dd5ad0466118acfa0cef2214b7a5. Initial tracked workspace was clean on main, matching origin/main.

## Steps

- [x] Read instructions, skills, current work and published two-cluster report; inspect source and current primary releases.
- [x] Freeze compatible native artifacts and render the official chart offline.
- [x] Implement explicit prerequisite installation and native storage/kernel qualification with receipts and identity checks.
- [x] Pass smallest offline guards before live work.
- [x] Run admission on a fresh owned cluster; retain all failures and confirm cleanup.
- [x] Repeat on a second fresh cluster if mandatory admission succeeds.
- [x] Review final diff, update qualification/runbook/current work, append handoff and prepare only tracked authorized changes for publication.

## Validation and progress

Primary GitHub release APIs report OpenShell v0.1.3 (2026-10-09), Agent Sandbox v1.0.6 (2026-10-08), Helm v4.3.0 latest and compatible Helm v3.22.0. OpenShell source e1f3c82caa3ed3b65de22889ae7ef32a774878ef explicitly supports v1beta1 discovery and native capability-probe. Agent Sandbox source cd0761d5001baaf293460cd382ee318744d6b249 exclusively serves v1beta1. Research metadata and registry observations: .runs/admission-research/. Bootstrap's externally pinned images still use native CRI pulls.

Initial restricted Docker access returned permission denied, and Git DNS resolution failed. Authorized network/local-Docker access then verified published HEAD and Docker 29.8.2/overlay2/cgroup v2 on kernel 6.14.0-37-generic. No host mutation. Referenced historical .runs/ and .state/ directories are absent; only the published outcomes and matching source can be rechecked here. No earlier raw-log re-audit claim.

Artifact preparation and official Helm render passed (.runs/artifacts/fd3c19d799f14d0ca53045b219edca86/). The offline chart generates an unused key-encryption Secret; evidence now redacts all Secret fields before persistence, and the first offline receipt/cache was sanitized. Native Kustomize custom-resource render/profile check passed (.runs/admission-offline-001/). Twelve configuration guards passed before cluster creation; two new ownership/redaction guards bring the suite to fourteen passed. Compilation and diff whitespace checks passed.

The first new cluster bootstrapped (.runs/bootstrap/48587d66455f4fd59d1900b1482b39c8/), but prerequisite install (.runs/admission-install/b198bec69a954e70892617cb4aabc613/) failed on SSA field conflicts with kind's existing client-side storage manager. Storage apply had partial delivery; Agent Sandbox apply was not reached. Scoped inventories are retained under .runs/admission-install-failure-inventory/. The bounded correction uses native client-side apply for kind-owned storage, retaining server-side apply for new Agent Sandbox objects. No force-conflicts or policy/kernel change. Failed-attempt cleanup was confirmed at .runs/bootstrap/4c34e35682ee452e839d7298787d7477/cleanup.json before a fresh retry.

Both fresh-cluster admissions passed: .runs/admission-host-001/ (93.53s) and .runs/admission-host-002/ (93.55s), with distinct node/PVC/PV/Pod identities, native Landlock ABI 6 and every required primitive true. Both fixture namespaces and PVs were cleaned up. The changed shared native-command/ownership boundary also passed its affected network consumers (.runs/network-admission-regression-001/, 3 passed in 157.77s, both namespaces cleaned). Scoped final inventories (.runs/admission-final-inventory/) found no fixture namespaces, Sandboxes, PVCs, PVs or gateway namespace. Exact cluster cleanup identities are in the [reviewed report](../../qualification/openshell-admission.md).

An interim make test-config failed one documentation-link guard (13 passed) because the report file was not yet created; after adding it, fourteen passed. Final native Helm digest pull also exposed a filename assumption: .runs/artifacts/88432a7b8ce34696beb6d970366ee164/ retained Helm exit zero and the file-lookup failure. Its digest-named archive matched the original frozen hash. Corrected native output discovery plus checksum validation passed at .runs/artifacts/c321f239b8f24a8eb82c754da3911158/. No OCI digest changed.

Final review used corsair-review across the bounded implementation, native-source/version selections, live receipts, failure/cleanup records and documentation. Findings fixed: preserve Secret-free chart evidence; use native Helm digest pull; handle native digest-derived filenames; follow kind's client-side storage field manager; verify cached render configuration as well as manifest hashes before install; checksum-pin the qualification kubectl; keep a timed-out kernel command unknown and its admission gate blocked. The final cache/render integrity guards were checked offline against the same admitted native resources (.runs/admission-render-equivalence.json); no runtime/policy/artifact inputs changed after the live runs. Final offline artifact/render evidence is .runs/artifacts/56992ccf20584ceaa3440535198de93d/. Fourteen guards, Python compilation and diff whitespace checks passed. No unresolved review finding; gateway/lifecycle/policy/toolchain/recovery and agents explicitly remain unrun.

## Decisions and next action

Prefer native capability-probe over bespoke syscall code. Stage the static binary using its supported copy-self init command into a memory emptyDir; never bake a supervisor into an application image. Gateway chart selection/rendering is independent work; do not install/connect gateway or begin 1B within this slice. Failed mandatory admission blocks dependent work without loosening requirements.

See [HANDOFF-0005](../handoffs/HANDOFF-0005-openshell-admission-qualified.md) and the [runbook](../../runbooks/openshell-admission.md). Next work is separately bounded 1B gateway/identity; this scoped plan is complete, not the full OpenShell milestone.
