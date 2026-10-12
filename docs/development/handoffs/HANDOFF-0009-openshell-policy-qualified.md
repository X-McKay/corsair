---
id: HANDOFF-0009
kind: handoff
title: Native OpenShell policy qualified
status: recorded
updated: 2026-10-11
related: [SPEC-0006, PLAN-0007, HANDOFF-0008, ISSUE-0003]
---

# Native OpenShell policy qualified

## Verified state

Branch codex/openshell-1d-policy; clean base 4222a60a0eb99a65eaaa43a02e641381e5c28881 matched published open draft PR #5 (codex/service-readiness). Current work is the tracked native 1D slice, prepared for authorized draft publication; this precommit snapshot does not invent a future SHA or assert a clean precommit tree. Resolve its committed source using git log -1 --format=%H -- docs/development/handoffs/HANDOFF-0009-openshell-policy-qualified.md and verify current remote/PR identity.

[PLAN-0007](../plans/PLAN-0007-openshell-policy.md) is complete. The [qualification report](../../qualification/openshell-policy.md) preserves selected artifacts, actual matrix, all failed attempts, timing limits and cleanup identities; the [runbook](../../runbooks/openshell-policy.md) requires three full invocations per fresh node. Native 1A–1D are bounded-qualified; full Milestone 1 is not complete. OpenShell/Agent Sandbox live installs are removed. 1E toolchains and 1F interruptions/limits/recovery remain unqualified, as do production tenancy, adapters, PydanticAI and Temporal.

## Validation and blockers

Before edits/live work, 30 offline guards passed. Final source has 61 passing offline guards, seven live tests collect without dispatch, and compilation/whitespace checks pass. Primary current release APIs retain OpenShell 0.1.3, Agent Sandbox 1.0.6, kind 0.33.0 and Calico 3.33.0; latest Helm 4.3.0 is unadmitted, so compatible 3.22.0 remains selected. Immutable schema/proxy/SDK/CLI/supervisor bytes were verified against primary e1f3c82 source. Kubernetes v0.35.8 networking API source confirms native omitted-empty egress semantics. Runtime lock, original policy, TLS/auth, chart/kernel/CNI inputs and uv.lock are unchanged.

The fixed operator canary image copies the already-pinned official curl artifact into isolated musl libraries on the fixed Ubuntu workload. Native no-network build and actual UID10001 DAC/content/curl controls pass; original container-ID absence confirmed. Docker config sha256:84e58098c371ecb4b6228f58b1b03737b7b69f3fc0625d3c1115ade24ad57ad9 and loaded/running manifest sha256:0664fcb5e7aee1ea247f4c3b0aeba2146f3f7fac356601fd63aa00cfaa5becb9 agree across both nodes. Build evidence cf5d492bafa94142b3d0dc9afb281d75 and source freeze .runs/policy-resume/final-source-hashes-004.json remain retained.

Final nodes a548d1a3-a504-4a89-a538-e3ab5e6e29c7 and 793c0bc0-2135-4bda-b783-577b84510fdd passed real storage/kernel and 3 CNI tests each before gateway/policy work: 91.29s/158.59s and 91.29s/159.48s. Linux 6.14.0-37-generic/containerd 2.3.4/Kubernetes 1.35.8, Landlock ABI 6 and every mandatory native capability field passed. Final policy-host-005 through010 passed 247.48s/192.37s/194.75s/321.73s/192.29s/323.68s, with 29 acknowledged SDK calls each and 1,510 native commands total. Twelve distinct policy sandboxes, 30 positive and 60 denied network markers, 30 fresh original-sandbox-bound native JSON endpoint denials, all loaded revisions 1/2/3 and actual server/SDK details reconciled. The matrix covers DAC-distinguished filesystem/symlink/write denial, admitted GET/POST, literal-IP/noproxy, three narrowed-method and three absent-endpoint trials, and independent outer CNI routes. All original Sandbox/CR/pod/PVC/PV, gateway/endpoint/private/forward cleanup confirmed.

Failed policy-host-001/002/003/004 remain failed in 80.04s/291.02s/192.42s/183.08s, attributed to global-absence oracle, missing executable, late JSON activation and omitted-empty egress oracle. First early source predates policy.json; audit uses its actual native error/no policy-create facts. Two failed image/library controls and initial incomplete canary-only preparation remain separate. Original IDs/absence are confirmed. All raw attempts, read-only inspection mistakes/corrections, source hashes and audits remain under .runs/policy-resume/, not Git. No failed control or partial source result counted as acceptance.

Final owned inventories policy-final-inventory-002/003 are empty. Original containers 612818bfa963572a56f1938645451bb0436a7ffedea73c26732dd08229e7fb1a and a43cd765332a51a93dc05ac6164267ce4fbf912f7dc4a5cfb1562fcfb9df0b3f removed with confirmation in bootstrap/6145b910223d4d699f180a12d854665c and 34d3020ff1384c5eb9276da5ab73e397. First investigation cluster also removed with confirmed original identity; its final inventory/teardown remains retained. Owner/kubeconfig/private gateway state/forwards absent. Cached images are inert evidence artifacts.

Native creates took 142.29s in failed run002 and 141.55s/140.18s in accepted runs008/010 within unchanged 180s budgets. Native workload readiness and delayed supervisor policy-fetch/enforcement facts are retained; cause/internal retry/queue timing remains unknown. These observations do not qualify recovery, low latency or fleet reliability. Historical original network raw runs remain absent and were not claimed as re-audited; new actual prerequisites were audited directly.

## Decisions and next steps

Use native Docker/kind, CLI and SDK surfaces; no production adapter, scheduler, provider protocol or execution fallback. Original create ID binds subsequent inspection/deletion. Supported scoped JSON logging must be atomically active before traffic. Omitted/empty egress only qualifies with explicit isolation and no grants. Three requests in one sandbox do not replace three full fresh-sandbox repetitions. No policy, TLS, pins, kernel requirements or command deadline were relaxed. Corsair review corrected all mandatory findings before final acceptance; no unresolved mandatory finding remains.

Existing authorization covers tracked draft publication above still-open PR #5; verify remote head and exact-head offline CI, do not merge or close issues. Never publish run/state/cache/tools, credentials or raw logs. Next separately bounded component is native 1E: select immutable compatible Python 3.12/pytest and Java 17/Maven/JUnit artifacts from primary sources and prove actual test execution/discovery, preserving attribution and identity cleanup. 1F must separately qualify interruption/resource limits/recovery before full native milestone acceptance. Every new node still requires real storage/kernel/CNI/gateway prerequisites; no application adapter, PydanticAI or Temporal work ahead of their gates.

## Continuation prompt

```text
Continue X-McKay/corsair after bounded native 1D policy qualification.
Read AGENTS.md, README, CURRENT, development/review/handoff skills, HANDOFF-0009,
SPEC-0006, PLAN-0007 and the policy report/runbook. Inspect git/source/publication,
current primary upstream releases, actual native receipts/source hashes, all
retained failed attempts and original-ID cleanup; do not trust handoff alone.
Verify six complete final-source policy repetitions on two distinct fresh nodes
and final namespace/volume/private/cluster absence. Native admission delays are
retained with unknown cause; recovery/reliability and full Milestone 1 are unproven.

Take only a separately bounded native 1E toolchain slice. Select compatible
immutable Python/pytest and Java 17/Maven/JUnit artifacts from primary sources;
require actual test execution, expected discovery IDs/counts and native reports.
Before OpenShell work, pass exact-node storage/kernel/CNI/gateway prerequisites.
No policy/TLS/pin/kernel weakening, workload replay after unknown delivery, or
adapter/PydanticAI/Temporal work before mandatory native gates. Preserve failures
and original-ID cleanup, run proportionate offline checks before live work,
review final diff/evidence, update work records/CURRENT, append a handoff and
publish only authorized tracked changes. Never commit .runs/, .state/, credentials
or raw logs; do not merge drafts or close external issues.
```
