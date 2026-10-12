---
id: HANDOFF-0006
kind: handoff
title: OpenShell gateway and identity qualified
status: recorded
updated: 2026-10-11
related: [SPEC-0004, PLAN-0004, PLAN-0003, HANDOFF-0005]
---

# OpenShell gateway and identity qualified

## Verified state

Branch codex/openshell-1b-gateway-identity, source/base 153ed1ee58a3a17b6ee941c12c14da74dfa7276e. At resume the 1A branch was clean and matched remote/draft PR #2; this branch isolates the next bounded slice. At handoff creation authorized tracked changes comprise a pinned native CLI, official-chart install gated by exact-node admission, local mTLS/identity/access probes and reviewed records. Resolve the committed/published revision with git log -1 --format=%H -- docs/development/handoffs/HANDOFF-0006-openshell-gateway-identity-qualified.md. Do not infer a future SHA or treat this precommit snapshot as a clean-tree claim.

[PLAN-0004](../plans/PLAN-0004-openshell-gateway-identity.md) is complete for bounded 1B only. The [report](../../qualification/openshell-gateway.md) and [runbook](../../runbooks/openshell-gateway.md) retain primary source/tuple selection, failures and actual scope. The previous two admission native reports/cleanup receipts were re-read; historical original network raw runs are absent, so no raw-log re-audit is claimed. Current native CNI regression evidence is retained.

Official OpenShell v0.1.3 chart/gateway/supervisor/runtime/Ubuntu pins, Agent Sandbox v1.0.6 and Helm 3.22.0 are unchanged. Matching CLI archive and binary are now checksum-locked. Linux amd64 kernel 6.14.0-37-generic, Docker 29.8.2/overlay2/cgroup v2, kind 0.33.0, Kubernetes 1.35.8/containerd 2.3.4 and Calico 3.33.0 remain the admitted host tuple. Native mandatory storage/kernel probes passed again before each fresh-cluster gateway installation. Default mTLS, verified TLS, explicit loopback forward, unauthenticated-user rejection, hard Landlock, no providers/network grants and native projected supervisor identity were preserved.

## Validation and blockers

Bounded 1B passed on distinct clean clusters: .runs/gateway-host-004/ (74.44s) and .runs/gateway-host-005/ (75.58s), each 59 native receipts plus three private exports with all credential output withheld. Native CLI/version/auth, wrong-trust/hostname rejection, no-identity API denial, actual Sandbox/supervisor/workload UID binding and mounts, and three CNI gateway-denial rounds over both Service/Pod routes with trusted in-cluster reachable controls all passed. Actual native policy/config admission accepted with the same retained hash; running workloads have no Secret/user/provider/Kubernetes-token mount, while required supervisor audience identity and CA-only projection remain. Native bootstrap/init is distinct from the running workload.

Prerequisite rechecks: .runs/gateway-prerequisite-001/ (93.84s) and 002/ (93.77s), both native admission/storage and fixture/PV cleanup passed. Affected ordinary-pod CNI regression .runs/network-gateway-regression-001/ passed three tests in 155.19s; both fixture namespace cleanups confirmed. Sixteen offline guards, native Helm render, compilation and whitespace checks pass. Review strengthened effective container security/ambiguous-pair and complete cleanup receipt guards; the first retained native metadata satisfies those added identity assertions in review-guard-audit.json, an explicit record audit. Final source hashes match the second live run; gateway-lock-equivalence.json distinguishes a scope-wording change from unchanged artifacts. Duplicate-evidence Make rejection preserved the prior JUnit before native dispatch.

All failed attempts remain: gateway 001 health-port assertion (11.15s), 002 native name-length rejection before provisioning (11.29s), 003 wrong pod-vs-container identity assertion after native Ready/configuration acceptance (21.84s). Every attempt's sandbox as applicable, namespace/PVs and port-forward cleanup is confirmed. Corrections changed the harness only; no security/pin/kernel weakening. Initial host UV-cache compile failed then passed with repo cache. One automatic permission review deadline expired before launch; its single permitted retry succeeded. A verbose failed traceback's host environment was withheld from private XML; narrow CLI environment and short tracebacks prevent credential exposure in subsequent failure evidence. Generated transport credential bytes never enter command receipts.

Both successful namespace/PV/private-state/port-forward cleanups and both cluster container-ID/absence checks are confirmed. Cluster cleanup receipts: .runs/bootstrap/0ee3c187175f48efab41773932de2771/cleanup.json and f256bfbf8d7f4fc1b8c86f64fbd15587/cleanup.json. Final .runs/gateway-final-inventory/ observed zero owned gateway/fixture namespaces and Sandbox/PVC/PV resources. Private gateway state and kind owner/kubeconfig are absent. No .runs/, .state/, cache/tools, credentials or raw private logs are publication artifacts.

## Decisions and next steps

Use native CLI/chart/controller/driver operations. Do not use setup prose's conflicting mTLS statement to disable authentication: source and actual acceptance/rejection establish the selected local behavior. This does not qualify production OIDC/tenancy or general escape resistance. Internal RPC/retry/queue metrics remain unknown; agent/model/durability checks are unrun.

Next, plan only 1C lifecycle/execution/transfers: select immutable compatible native SDK artifacts, use supported native create/get/exec/transfer/delete and expected-sandbox-ID waits, preserve exact outputs/nonzero exits/digests and unknown delivery, and qualify repeated identity-checked cleanup. Do not begin application adapters, policy/toolchain/recovery integration, PydanticAI or Temporal. Recheck prerequisite/1B boundaries on changed runtime inputs. Existing authorization covers tracked publication; publish separately above the still-open 1A branch rather than merge either draft PR.

## Continuation prompt

```text
Continue X-McKay/corsair from bounded 1B gateway/identity qualification. Read
AGENTS.md, README, docs/development/CURRENT.md, development/review/handoff skills,
HANDOFF-0006, PLAN-0004 and the platform/admission/gateway reports. Inspect git,
source, publication and current primary upstream releases. Verify retained
native receipts, failures and immutable cleanup identities; handoff is context.

Plan only 1C native lifecycle/execution/transfers. Pin compatible immutable SDK,
CLI and workload artifacts and use supported native APIs, including expected
sandbox-ID waits. Revalidate required admission on any new/changed tuple. Retain
exact command output/exit and file digests, all failed attempts, uncertain
completion and confirmed or unconfirmed cleanup. Do not weaken policy/TLS/pins/
kernel requirements or integrate adapters, agents or Temporal before their
mandatory gates pass. Run smallest offline checks before live work, update the
report and work records, review the final diff, append a new handoff and publish
only tracked authorized changes. Never commit run/state artifacts, credentials
or raw private logs.
```
