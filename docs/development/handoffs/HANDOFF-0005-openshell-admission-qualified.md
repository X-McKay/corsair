---
id: HANDOFF-0005
kind: handoff
title: OpenShell native admission qualified
status: recorded
updated: 2026-10-11
related: [SPEC-0003, PLAN-0003, PLAN-0001, HANDOFF-0004]
---

# OpenShell native admission qualified

## Verified state

Branch codex/openshell-1a-admission; source/base revision 1affbba9fc80dd5ad0466118acfa0cef2214b7a5, initially clean on main and matching the remote. Resolve this work's published revision with git log -1 --format=%H -- docs/development/handoffs/HANDOFF-0005-openshell-admission-qualified.md. At handoff creation tracked changes comprise immutable artifacts, explicit native prerequisites, one storage/kernel qualification fixture/test, narrow ownership/evidence guards and reviewed records. Ignored .runs/, .state/, tools, caches and virtual environment are not publication artifacts.

[PLAN-0003](../plans/PLAN-0003-openshell-admission.md) is complete only for the remaining bounded 1A slice. Agent Sandbox v1.0.6 core and pinned kind local-path storage were installed on two fresh clusters. The trusted OpenShell v0.1.3 runtime was staged separately into the pinned native default Ubuntu workload. Native storage/kernel admission passed twice on the qualified host: Linux amd64 6.14.0-37-generic, Docker 29.8.2/overlay2/cgroup v2, kind v0.33.0, Kubernetes v1.35.8/containerd 2.3.4, Calico v3.33.0. The official chart and matching gateway/supervisor images are selected and rendered offline only. Helm v3.22.0 follows the setup docs' 3.x requirement; newest Helm v4.3.0 is unadmitted.

Gateway, authenticated boundary service, user identity, application policy, lifecycle/toolchain/recovery, production storage/tenancy, adapters, PydanticAI and Temporal remain uninstalled/unqualified. All three clusters created in this session, both admission fixtures/PVs and both network regression fixtures were cleaned up with identity/absence confirmation. Owner/kubeconfig state is absent. No credentials were staged into workloads or exported.

## Validation and blockers

The [reviewed admission report](../../qualification/openshell-admission.md) contains exact pins, identities, evidence references, measurements and primary sources. Native admission passed in 93.53s and 93.55s on distinct node/PVC/PV/Pod identities. Both runs verified PVC marker persistence across a controller-created replacement Pod and every native probe result, including hard Landlock ABI 6 allow/deny, seccomp notification/atomic addfd, nondumpable-parent/same-UID-child memory access, non-TSYNC listener/socket confinement, self-protection and local TCP/UDP/DNS controls. Primitive success does not qualify an authenticated OpenShell session.

Fourteen offline guards pass, native Helm/Kustomize renders pass, compilation and git diff --check pass. The affected shared network consumers also passed: three live tests in 157.77s (.runs/network-admission-regression-001/), with both fixture cleanups confirmed. No model or durability checks ran. Final offline guard/render validation uses the same admitted inputs; .runs/admission-render-equivalence.json records that comparison.

Preserved failures: restricted Docker/DNS access before authorized inspection; storage SSA conflicts with kind's existing client-side manager (.runs/admission-install/b198bec69a954e70892617cb4aabc613/), inspected partial delivery and confirmed failed-cluster cleanup; a transient documentation link-guard failure before report creation; native Helm digest filename lookup failure (.runs/artifacts/88432a7b8ce34696beb6d970366ee164/), whose actual bytes matched the frozen hash. The chart generates an unused Secret during offline rendering; all retained render evidence now redacts Secret fields before persistence, including sanitizing the first receipt/cache. None of these failures proved an application or kernel defect.

Successful run evidence: .runs/admission-host-001/ and .runs/admission-host-002/. Cluster cleanups: .runs/bootstrap/7f3c282f57f54b09ac1d10ae7f056934/cleanup.json and .runs/bootstrap/c12ccbce1df547baa84cfbc961dc3d69/cleanup.json, both confirmed. Final inventories: .runs/admission-final-inventory/. The prior published ordinary-pod two-cluster record/source were verified against remote HEAD; its historical raw directories are absent here, so no raw-log re-audit is claimed.

## Decisions and next steps

Keep native CRI pulls for digest-pinned images. Use kind's native client-side apply for its own storage objects and server-side apply for new Agent Sandbox core resources; no force-conflicts/adoption/repair. Use native Helm pull by immutable OCI digest and archive verification. Match the Kubernetes driver's capability-free profile and native capability-probe rather than bespoke syscalls. Do not expand policy, add capabilities or loosen kernel/TLS/pin requirements.

Next, take only a focused 1B gateway/identity plan: use supported official chart installation with discovery preflight enabled, selected artifacts, native readiness, verified TLS, explicit local authentication/access isolation and actual generated supervisor/workload identities/mounts. No transport credentials belong in .runs/ or Git. Revalidate required 1A prerequisites on any new/changed tuple. Do not integrate application adapters, agents or Temporal or claim lifecycle/policy qualification from these primitive probes.

## Continuation prompt

```text
Continue X-McKay/corsair from the qualified remaining 1A foundation. Read
AGENTS.md, docs/development/CURRENT.md, the development/review/handoff skills,
HANDOFF-0005-openshell-admission-qualified.md, PLAN-0003 and both qualification
reports. Inspect branch/status/source and current primary upstream releases;
verify available receipts and preserve every failure and identity-checked cleanup.

Take only a focused 1B gateway/identity slice: supported native installation with
immutable compatible artifacts, Agent Sandbox discovery preflight enabled,
verified TLS, explicit local auth/access isolation, and actual generated
supervisor/workload identities and mounts. Plan before edits, run the smallest
offline checks before live work, and stop dependent work on any failed mandatory
admission/identity boundary. Do not weaken policy, TLS, pins or kernel requirements.
Do not begin adapters, PydanticAI or Temporal. Keep credentials outside workloads,
run evidence and Git. Update records/report/CURRENT, review the final diff, append
a new handoff and publish only tracked authorized changes; never publish .runs/,
.state/, credentials or raw private logs.
```
