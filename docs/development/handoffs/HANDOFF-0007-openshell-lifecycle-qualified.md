---
id: HANDOFF-0007
kind: handoff
title: Native OpenShell lifecycle execution and transfers qualified
status: recorded
updated: 2026-10-11
related: [SPEC-0005, PLAN-0005, ISSUE-0003, HANDOFF-0006]
---

# Native OpenShell lifecycle execution and transfers qualified

## Verified state

Branch codex/openshell-1c-lifecycle, source/base 59afa3fd3e69148ceb1f7ae2dd2deefc75785dcd. Resume was clean and matched remote/open draft PR #3, based on still-open 1A PR #2. This tracked change adds the matching immutable official SDK wheel/native uv dependency lock, shared gateway qualification fixture and bounded native 1C probes, reviewed report/runbook and work records. Resolve the committed/published work with git log -1 --format=%H -- docs/development/handoffs/HANDOFF-0007-openshell-lifecycle-qualified.md; do not invent a future SHA or treat this precommit snapshot as a clean-tree claim.

[PLAN-0005](../plans/PLAN-0005-openshell-lifecycle.md) is complete for bounded 1C; the [qualification record](../../qualification/openshell-lifecycle.md) preserves exact scope/identities and the [runbook](../../runbooks/openshell-lifecycle.md) uses native setup/probes. Host/kernel/runtime/image/policy/TLS/auth inputs remain the admitted Linux amd64 tuple. Primary current APIs still select OpenShell v0.1.3 and Agent Sandbox v1.0.6; compatible selected Helm 3.22.0 remains unchanged rather than latest 4.3.0. Official SDK wheel SHA-256 d1eaa6abcd714e2f19d4a8ecbc2079bebeb7b56d81e9f8d3f5a9b5165ed1956c matches the downloaded artifact/uv lock. Installed SDK source equals inspected immutable upstream (.runs/1c-sdk-source-audit.json). Native Python SandboxClient provides lifecycle/exec/expected-ID waits; curated transfers are absent, so native CLI transfers are used. No application adapter or custom protocol.

Prior 1B native receipts/JUnit/immutable cleanup were read; first prior run lacks source-hash file, second matches final source at resume. Original network raw evidence is absent, so only published source/record verification is claimed. New .runs/1c-resume-audit.json retains the explicit distinction. Handoff is context, not a receipt.

## Validation and blockers

Eighteen offline guards passed before live work; native lifecycle collection selected one test among six, compilation/whitespace passed. Fresh node b1460a20-3b3b-4569-8beb-bf45a4fac36b admission passed in 93.30s (.runs/lifecycle-admission-001/) and complete CNI controls in 152.66s (.runs/lifecycle-network-002/). Second node 43ec384a-1880-4332-be07-e37cc20ace8e admission passed in 93.90s (002/) and complete CNI in 150.33s (.runs/lifecycle-network-005/). Both native reports have ABI 6/all required controls true and fixture/PV cleanup; CNI pass records have actual reachable controls, three denial rounds and rollback, not merely Ready/version checks.

Counted native 1C runs .runs/lifecycle-host-002/ (118.42s) and 003/ (124.55s) each passed 3 new SDK sandbox repetitions after the same mandatory 1B TLS/auth/generated-identity/CNI gateway controls. Each retains 32 top-level SDK and 122 native command receipts plus private credential-export receipts. Exact stdout/stderr and exit 23, explicit workdir/env/stdin read/write, native /sandbox workdir and 1042-byte binary CLI roundtrip SHA f5882d32b05def4b79512eb76c57c7ee9cd8ca639e6ab69c359dbdff25560e04 all passed. Each original native sandbox ID/CR/workload/supervisor/PVC/PV identity was observed and deletion/reclamation confirmed before another repetition. Same accepted hard-policy hash/config/provider-env revisions; no providers or workload credentials. Both passing source hash sets match final harness/SDK lock; .runs/1c-final-evidence-audit.json reconciles actual JUnit/results/IDs/cleanup/source.

Retained failures/limits: prerequisite preflight 6349237ce86a4263b7805d2fc96ab4c1 dispatched before bootstrap finished and rejected Calico not Ready without install mutations; subsequent install only after bootstrap passed. Network 001 (1 failed/2 passed, 123.32s) initial ingress Service curl 7; 003 (1 failed/2 passed, 124.70s) initial egress Service curl 28; 004 (2 failed/1 passed, 89.90s) both initial Service curl 7. Every failed fixture cleanup confirmed; no failed control counted as denial. Three diagnostic fresh fixtures reached all initial routes with unchanged inputs and native endpoint/proxy data retained (.runs/service-readiness-diagnostic-001/); failure did not reproduce. Native proxy iptables/minSyncPeriod 1s supports only a convergence hypothesis. Final complete 005 passed after those new observations. [ISSUE-0003](../issues/ISSUE-0003-service-control-readiness.md) remains open for initial Service readiness reliability; no network/CNI/source repair was implemented.

Lifecycle 001 passed pytest in 111.04s but is coverage incomplete and excluded from full qualification: per-sandbox workspace PVC/PV IDs/disappearance were unobserved. Actual CR volumeClaimTemplates/pod claims disproved an assumed shared lifetime. Added capture/reclamation guards, then both counted runs passed; no policy/runtime requirement changed. First incomplete run final namespace/PV/private/forward cleanup and subsequent zero-resource inventory are retained without invented PV IDs. Restricted-network uv metadata refresh failed before test/compile dispatch; cached UV_OFFLINE=true/--offline guards/compilation passed. Final record guard initially failed missing ISSUE-0003 template headings (1 failed/17 passed, 0.09s); corrected to canonical template before publication. Read-only source-path/audit mistakes are explicitly retained in .runs/1c-inspection-history.json, not native runtime failures.

Both final inventories show zero owned fixture/gateway namespaces and Sandbox/PVC/PV and private gateway state absent. Forward terminate/reap confirmed. Cluster cleanup .runs/bootstrap/f9ef5e567a2e4059b5f107022de15270/cleanup.json confirms container 1731dd586eccb9edec5e501a7b0ccd0172a1f49fa49e2fadb1b739044c184bb7 absent; second ab3c2e4caa57482a8e0d589539a073a7 confirms 00331df785ed42e851d0a2b9a9c876719dc4dae925bd12a7041b260d5e544a30 absent. Kind owner/kubeconfig and private gateway state are removed. No run/state/cache/tool files, credentials or raw logs are publication artifacts.

## Decisions and next steps

Corsair review found no unresolved mandatory 1C finding. Bounded runtime correctness/consistency is admitted after actual controls; Service startup reliability, general escapes/fleet reliability, internal RPC/retry/queue metrics and production tenancy are not. Native SDK wait_ready may return Completed: require Ready/ID explicitly. Expected-ID wait_deleted accepts absence of original even if name reused: also require empty workspace and actual immutable CR/pod/PVC/PV disappearance. No blind retry of unknown mutation/exec delivery.

Next bounded action is ISSUE-0003 native Service readiness diagnosis with EndpointSlice/proxy timing before further live policy qualification. 1D planning may proceed independently; new/changed runtime work requires actual mandatory storage/kernel/CNI/gateway controls. Do not weaken policy/TLS/pins/kernel criteria, count diagnostics as qualification or begin adapters, agents, PydanticAI or Temporal. Existing authorization covers tracked publication; publish a separate draft PR above still-open 1B PR #3, without merging any draft.

## Continuation prompt

```text
Continue X-McKay/corsair from bounded 1C native SDK lifecycle/exec/CLI-transfer
qualification. Read AGENTS.md, README, CURRENT, development/review/handoff skills,
HANDOFF-0007, PLAN-0005, the qualification record and ISSUE-0003. Inspect git,
source, publication and current primary releases; verify retained native
receipts, failed/incomplete attempts and immutable cleanup, not handoff alone.

Take one bounded native initial-Service-readiness investigation under ISSUE-0003.
Preserve actual PodIP/Service controls, EndpointSlice/proxy timing, failed
attempts and UID-checked cleanup; no speculative CNI repair or policy/TLS/pin/
kernel weakening. 1D planning can proceed independently, but dependent live
work needs successful mandatory real controls on the exact owned node. Keep
policy/toolchain/recovery integration and application adapters/agents/Temporal
unadmitted until their own gates pass. Run smallest offline checks before live
work, review final diff, update reports/work records/CURRENT and append a new
handoff. Publish only tracked authorized changes; never run/state/credentials/
raw logs. Existing draft PRs are not authorization to merge them.
```
