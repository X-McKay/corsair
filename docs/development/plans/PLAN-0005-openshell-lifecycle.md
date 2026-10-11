---
id: PLAN-0005
kind: plan
title: Qualify native OpenShell lifecycle execution and transfers
status: complete
updated: 2026-10-11
related: [SPEC-0005, PLAN-0004, HANDOFF-0006, ISSUE-0003]
---

# Qualify native OpenShell lifecycle execution and transfers

## Objective and dependencies

Implement only [SPEC-0005](../specs/SPEC-0005-openshell-lifecycle.md). Base/source 59afa3fd3e69148ceb1f7ae2dd2deefc75785dcd; clean resume branch matched remote and open draft PR #3. New branch codex/openshell-1c-lifecycle. Retained 1B JUnit/native receipts and namespace/PV/cluster cleanup were read: distinct successful runs 004/005, second run source hashes match all five files. First run predates source hashing; do not invent it. Audit .runs/1c-resume-audit.json. Original published two-cluster network record remains verified at source/publication level with historical raw evidence absent. No surviving owned cluster/private state.

## Steps

- [x] Verify publication, retained boundary evidence and current primary releases; inspect native SDK/CLI capabilities and official wheel hash.
- [x] Pin SDK/dependency artifacts and implement bounded native lifecycle probes with shared gateway fixture.
- [x] Run offline guards before live work; fresh-cluster admission/gateway and three lifecycle repetitions with all failed attempts/cleanup retained.
- [x] Repeat mandatory boundaries and three lifecycle repetitions after second clean creation.
- [x] Review final diff, report/runbook, CURRENT and new handoff; publish only tracked authorized changes.

## Validation and progress

Current primary APIs: OpenShell v0.1.3 (2026-10-09), Agent Sandbox v1.0.6 (2026-10-08), Helm latest v4.3.0; selected admitted 3.22.0 unchanged. Downloaded official SDK wheel matches published d1eaa6... SHA; METADATA requires Python >=3.11 and native dependencies. One read-only audit initially assumed first-run source-hashes.json existed; corrected to explicitly record it absent and completed both audits. make test-config: 18 passed (0.18s); lifecycle collection: one selected/six total, no live dispatch; Python compilation and whitespace pass. Native shared workspace storage outlives individual sandboxes, so require per-sandbox CR/pod disappearance and final identity-checked workspace PVC/PV reclamation. First bootstrap .runs/bootstrap/38cdb8d2c82241e9b46a7a561e0c5eef/ passed. Prerequisite preflight was dispatched before bootstrap completion and rejected Calico not Ready without installation mutations (.runs/admission-install/6349237ce86a4263b7805d2fc96ab4c1/); preserved as orchestration failure. Bootstrap subsequently confirmed actual readiness before a new install attempt. Native admission .runs/lifecycle-admission-001/ passed (93.30s), namespace/PV cleanup confirmed. CNI rerun dispatched after completion. Before lifecycle dispatch, inspected CLI workspace-root restriction and corrected transfer probes to use native discovered workdir rather than /tmp; unchanged policy. Offline guards/compilation pass after that correction. No gateway/lifecycle dispatch yet.

## Decisions and next action

Use native SandboxClient and supplied protobuf spec types, exact mTLS, no provider/environment autodiscovery and CLI transfers. SDK errors retain upstream structure without ambient environments; unknown create/delete/exec delivery stops dependent work. The existing gateway setup/controls/teardown becomes a pytest fixture for its demonstrated second consumer; no application adapter or generic scheduler. SDK lock changes require new admission on each new node. Begin offline guards then explicit native provisioning.

CNI .runs/lifecycle-network-001/ failed its ingress positive Service control (curl 7, immediate connection refused) after successful PodIP GET/POST. Ingress namespace UID-checked cleanup confirmed; test did not reach ingress policy assertions. Dependent work remains stopped; allow the egress test/cleanup to finish, then a separate fresh-fixture attempt under unchanged inputs. Do not treat failed control as enforcement evidence or erase this attempt.

Native transfer source contains its own bounded transport retry handling; receipts measure top-level CLI operations, not hidden RPC/SSH attempts. The qualification harness adds no blind retries. Before dispatch, normalized CLI policy metadata was inspected: empty network_policies is omitted, so assert absent-or-empty alongside explicit inert SDK spec and no providers.

CNI fresh-fixture rerun .runs/lifecycle-network-002/ passed all 3 tests in 152.66s with both fixture cleanups confirmed, unchanged policy/runtime/source. Prior 001 remains 1 failed/2 passed (123.32s). Gateway installation may now proceed from successful same-node admission; no pass inferred from failed control.

First .runs/lifecycle-host-001/ passed pytest/native exec+transfer in 111.04s (3 repetitions, 32 SDK calls) and gateway namespace/final PV/private/forward cleanup. Final review found the assumption of shared workspace PVC ownership incorrect: retained actual CR volumeClaimTemplates and pod claims are per-sandbox. Thus 001 is evidence-coverage incomplete for per-sandbox PVC/PV identity cleanup and is not counted as fully qualified. Retain it unchanged. Added native claim/PV identity capture and per-repetition disappearance checks; first cluster must rerun before second clean creation. No runtime/policy input changed. Earlier shared-storage wording above is superseded by this verified ownership correction.

UV metadata refresh attempted network access during the post-review make test-config/compile command and failed in the restricted network sandbox before test dispatch. Re-ran with UV_OFFLINE=true and uv --offline against the already installed/hash-locked dependencies: 18 guards (0.10s), compilation/whitespace passed. Gateway reinstall bfa6ffc7c9a947d7bcab7acfd2e0ca75 passed under unchanged node/runtime inputs; stricter .runs/lifecycle-host-002/ dispatched only after those offline guards passed. .runs/lifecycle-first-inventory/ observes zero PVC/PV/Sandbox items after the coverage-incomplete first run, without inventing its unobserved per-sandbox PV IDs.

Stricter first-node run .runs/lifecycle-host-002/ passed in 118.42s: mandatory gateway controls plus three new native SDK repetitions with captured CR/pod/PVC/PV immutable IDs and confirmed disappearance, exact output/nonzero exit, read/write and binary SHA-256 roundtrip. Final namespace/remaining PV/private-state/forward cleanup confirmed. Source hashes match current harness. First-cluster final native inventory and immutable container deletion are next; only then second clean creation.

First final inventory .runs/lifecycle-first-final-inventory/ confirms zero owned fixture/gateway namespaces and Sandbox/PVC/PV, private gateway state absent; first immutable container cleanup .runs/bootstrap/f9ef5e567a2e4059b5f107022de15270/cleanup.json confirms container 1731dd586eccb9edec5e501a7b0ccd0172a1f49fa49e2fadb1b739044c184bb7 absent. Second bootstrap .runs/bootstrap/39df1f509471495286d390dbd9a9c161/ passed before installing prerequisites.

Second prerequisite install .runs/admission-install/5a33d2be660e4b3d8546df8e95004139/ passed; .runs/lifecycle-admission-002/ passed storage/native kernel in 93.90s with fixture/PV cleanup. CNI .runs/lifecycle-network-003/ now runs before second gateway dispatch.

Second-node CNI .runs/lifecycle-network-003/ retained 1 failed/2 passed in 124.70s: egress initial reachable control curl 28 before egress policy application; ingress passed, both UID-checked fixture cleanups confirmed. Dependent gateway/lifecycle stayed unrun. Scoped native ownership/platform/fixture-absence inventory .runs/lifecycle-second-cni-inventory/ precedes one separate fresh-fixture attempt .runs/lifecycle-network-004/ with unchanged inputs. These control failures limit readiness/convergence reliability; they are not policy-denial evidence.

Recorded the recurring initial Service-control readiness observation in [ISSUE-0003](../issues/ISSUE-0003-service-control-readiness.md); its root cause and startup reliability remain unqualified even if complete later fresh-fixture controls pass. No network fixture/policy repair is included in this slice.

Second-node network 004 also failed both initial Service controls (curl 7), 2 failed/1 passed in 89.90s; both fixture cleanups confirmed. 1C second repeat is blocked, not dispatched. Native diagnostic .runs/service-readiness-diagnostic-001/ now observes unchanged fixture PodIP/Service controls, actual EndpointSlices/proxy config/logs and bounded synthetic GET reachability with every request retained; this is diagnosis, not a replacement CNI pass. Kubernetes v1.35 primary docs describe asynchronous minimum proxy resync; that supports a hypothesis, not a root-cause claim. Any correction must preserve actual reachable controls/server-log coverage and all denial trials, with no runtime/policy change.

Native diagnostic completed three independent new fixtures: every initial PodIP/Service GET/POST returned 0 with expected response; extra observed Service GET/log coverage passed, all UID-checked cleanups confirmed. Native proxy config is iptables/minSyncPeriod 1s; current v1.35 primary docs describe asynchronous resync, but the failure did not reproduce and root cause remains unproven. No readiness/CNI/source correction is justified or implemented. Based on these new observed reachable controls, one final complete unchanged CNI suite .runs/lifecycle-network-005/ is dispatched; diagnosis is not qualification and all prior failed suites remain retained. If it fails, clean the cluster and publish 1C as blocked/incomplete rather than retry more or weaken criteria.

Final unchanged second-node CNI .runs/lifecycle-network-005/ passed all three tests in 150.33s with both namespace cleanups confirmed. Actual reachable controls/denials/rollback now resolve the dependency for bounded runtime execution on this node, not the initial Service startup reliability issue. Prior 003/004 failures remain retained and ISSUE-0003 stays open. No network fixture/runtime/policy code changed. Second native gateway installation now proceeds only from this complete pass and same-node successful admission.

Second native gateway install ec857aa4e4ca42cc927c34545797014b passed. Frozen .runs/lifecycle-host-003/ passed in 124.55s: mandatory 1B controls plus 3 fresh SDK lifecycle/exec/CLI transfer repetitions; every original CR/pod/PVC/PV disappearance and final namespace/PV/private/forward cleanup confirmed. Both counted passes 002/003 each have 32 SDK observations and 122 native command receipts. Final .runs/lifecycle-second-final-inventory/ has zero owned fixture/gateway namespaces, Sandbox/PVC/PV and private gateway state absent. Cluster cleanup ab3c2e4caa57482a8e0d589539a073a7 confirms container 00331df785ed42e851d0a2b9a9c876719dc4dae925bd12a7041b260d5e544a30 absent. Final evidence audit .runs/1c-final-evidence-audit.json checks both JUnit/gateway/lifecycle results, all cleanup flags, distinct immutable IDs and all source hashes matching final code/SDK lock. Installed SDK source matches inspected immutable upstream (.runs/1c-sdk-source-audit.json).

Corsair final self-review found no unresolved mandatory 1C issue: native SDK/CLI only, frozen operator inputs, same mandatory private/auth/kernel requirements, preserved failed/unknown attempts, independent actual cleanup. The initial workspace-PVC evidence gap was corrected and excluded from qualification; the network-readiness issue remains open, with no repair or unsupported reliability claim. The reviewed [qualification record](../../qualification/openshell-lifecycle.md) is authoritative for bounded coverage. Append HANDOFF-0007 and update CURRENT; publish this tracked change as a separate draft above still-open PR #3, without merging drafts. New dependency pins are preparation/selection, not native qualification by themselves.

Final offline record guard initially returned 1 failed/17 passed (0.09s) because ISSUE-0003 omitted required template section names. Corrected headings to the canonical issue template; no runtime/source input changed. Failure retained in inspection history, final checks rerun before publication.

Final UV_OFFLINE=true make test-config: 18 passed in 0.08s; compilation and git diff --check passed. Expected duplicate-evidence Make rejection preserved original passing JUnit SHA before any dispatch (.runs/1c-duplicate-guard.json). Final host inventory confirms no kind container, owner/kubeconfig or private gateway state. Parent remote/PR #3 still exactly 59afa3fd3e69148ceb1f7ae2dd2deefc75785dcd and open/draft; no existing remote 1C branch. All changed tracked/authorized files reviewed; private directories are untracked.

Staged whitespace review flagged one trailing space in the newly tracked report (not covered by earlier unstaged checks); removed before commit. No code/runtime/source-hash change.
