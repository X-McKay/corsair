---
id: PLAN-0008
kind: plan
title: Qualify native OpenShell toolchains
status: complete
updated: 2026-10-11
related: [SPEC-0007, PLAN-0007, HANDOFF-0009, HANDOFF-0010]
---

# Qualify native OpenShell toolchains

## Objective and dependencies

Implement and qualify [SPEC-0007](../specs/SPEC-0007-openshell-toolchains.md), native 1E only. Clean base b194341a9d44f30e0371204cd36a534370e954ef matched published open draft PR #6 and successful exact-head CI 38160536248. Branch codex/openshell-1e-toolchains. Six prior 1D actual raw/source/cleanup receipts and the published record were audited before edits; a handoff was not treated as proof. Historical original network raw files remain absent and are not claimed as re-audited.

## Steps

- [x] Verify source/git/publication, actual prior evidence and primary release/image/package sources before edits.
- [x] Prepare fixed operator artifacts and native probes; run relevant offline guards before live work.
- [x] Pass exact-node prerequisites and complete unchanged-source 1E on two fresh clusters; retain all failed attempts and identity cleanup.
- [x] Review final diff/evidence, update qualification/runbook/CURRENT and append handoff; prepare tracked authorized stacked draft publication. Verify remote identity and exact-head offline CI after push.

## Validation and progress

UV_OFFLINE=true make test-config: baseline 61 passed/0.10s; initial 70 passed before live dispatch; final 84 passed after focused evidence corrections. Native image preparation, no-network real Python/Java controls, original container absence and immutable local loads passed. Both distinct nodes passed real storage/kernel and three CNI tests before gateway/identity and toolchains. Toolchain-host-007 and 008 each passed the complete unchanged-source matrix in two fresh native sandboxes. Seventy-two SDK calls were acknowledged. Full original Sandbox/CR/pod/PVC/PV, endpoint/gateway/private/forward and both immutable cluster removal is confirmed. Eight live tests collect, one toolchain selection; compilation and whitespace checks pass.

All six failed attempts remain failed and separately attributed: strict Service control after fixture mutation; missing native event with wrong HTTP-forward oracle; wrong mediated-event prefix; host checksum oracle editing error; too-narrow client exception oracle; and native Maven prefix-resolver diagnostic differing from assumed offline wording. All 95 failed-run SDK calls were acknowledged and original-ID cleanup confirmed. No partial source counted as acceptance. [The report](../../qualification/openshell-toolchains.md) carries exact timings, identities, artifacts, upstream sources, matrix, corrections and limits. Raw audits/source freezes remain in .runs/toolchain-resume/, never Git.

Actual commands: make toolchain-images; on each fresh cluster make kind-up, admission-install, toolchain-images-load, qualify-admission, qualify-network, openshell-install and qualify-toolchain with distinct same-node evidence paths; final empty owned inventory and make kind-down, followed by immutable original-container absence. Final read-only audit reconciled native JUnit/SDK output, loaded policy, fresh upstream event/destination, source/image hashes, prerequisite capabilities and all cleanup. Final tracked publication uses this branch above codex/openshell-1d-policy; resolve its committed SHA with git and verify publication rather than treating this precommit record as a receipt.

## Decisions and next action

Fixed official amd64 Python 3.12.15/pytest 9.0.2 and Maven 3.10.0/Temurin 17.0.20.1+1/JUnit 5.14.4 artifacts are admitted only for this matrix. Compatible Helm 3.22.0 remains selected despite latest 4.3.0; current OpenShell 0.1.3/Agent Sandbox 1.0.6/kind 0.33.0/Calico 3.33.0 and runtime locks are unchanged. Native preparation, CLI transfers, SDK execution and original identity/cleanup controls suffice; no production adapter or repair framework. No policy/TLS/pins/kernel/deadlines were weakened. Final review has no unresolved mandatory finding.

Next separately bounded slice is native 1F interruptions/limits/recovery; no full milestone/reliability claim or adapters/PydanticAI/Temporal work ahead of mandatory gates. Existing native admission delays have unknown cause. Every new node still needs real storage/kernel/CNI/gateway prerequisites. See [HANDOFF-0010](../handoffs/HANDOFF-0010-openshell-toolchains-qualified.md).
