---
id: HANDOFF-0052
kind: handoff
title: Fully live fixture E2E over the OpenShell test workspace
status: recorded
updated: 2026-10-13
related: [PLAN-0034, SPEC-0031, SPEC-0032, SPEC-0025]
---

# Fully live fixture E2E over the OpenShell test workspace

## Verified state

Branch `claude/live-e2e-sandbox-runner-w1edrl` from main `0d9bb5a`, PR #33. Delivered: `evals/fixture_e2e/sandbox.py` (`Runners` factory over `OpenShellTestWorkspace`, one fresh sandbox per development/baseline/candidate run; `sandbox_case` with the sandbox environment declaration), `record_run` shared by the reviewed CLI and the live gate, `tests/qualification/test_fixture_e2e.py` (`make qualify-fixture-e2e`), `tests/qualification/test_credential_placeholder.py` plus `credential_scan.py` (`make qualify-credential-placeholder`), offline tests. No contract, policy, pin or agent prompt changed. The gate verdict stays witness-limited (`completed`/`inconclusive`/`not_verified`) until SPEC-0033 lands.

## Validation and blockers

- `make test-config`: 781 on `0d9bb5a`, 786 on this branch. PR CI (offline-guards) green on every pushed commit.
- RIG0, fresh kind node (network 3/3, admission 1/1), one `make qualify-fixture-e2e` run with three fully live runs on the PLAN-0031 provider config and main's prompts: exit 0, 990.6 s. Control complete and admitted; live runs reached the gate 2/3 (planning cap once), live-1 security test inverted and named `baseline_not_reproduced` by the gate, live-3 over-claim rejected. All sandboxes cleaned up. Details in PLAN-0034. Evidence `.runs/live-e2e-20261013/` in `/home/al/git/corsair-live-e2e` on RIG0 (private, git-ignored).
- Storage quota: not reachable through the 0.1.3 gateway (`local-path` class, no node quotas, `allow_driver_config=false`); a memory `sizeLimit` emptyDir enforces bytes with `ENOSPC` and inodes only via the memory cgroup (plain pod only). SPEC-0025 stays blocked on storage.
- Credential placeholder: `cred-001` setup error (missing fixture import), `cred-002` refused by the gateway (`generic` profile not in scope). The gate now imports its own profile; its next live run (`cred-003`) had not run when this handoff was written. In-sandbox placeholder form and host-bound substitution remain unverified; egress substitution is not implemented in the gate.
- The RIG0 session's auto-mode permission check refused ad hoc TLS exports and the gates until the owner added allow rules for the two make targets in the worktree's `.claude/settings.local.json`. Each gate's gateway fixture uninstalls the gateway at teardown; run `make openshell-install` before the next gate.

## Decisions and next steps

Live agent outcomes are recorded, not asserted; the scripted control is asserted so route failures stay attributable. Agent prompt and budget changes belong to PLAN-0035 (reconcile with its stage-profiles option in the shared runner). Next: run `cred-003`; rerun the E2E gate on PLAN-0035's prompts and, once SPEC-0033 captures a witness, with it; decide a storage enforcement route (gateway driver config or upstream) before SPEC-0025 live work.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then PLAN-0034, SPEC-0031, SPEC-0032 and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. On a fresh admitted RIG0 node (make openshell-install before each gate), run make qualify-credential-placeholder once and record the placeholder form, scan scopes and cleanup in PLAN-0034; then rerun make qualify-fixture-e2e on the current agent prompts. Do not claim storage enforcement or private-repository support while SPEC-0025's blockers hold. Run make test-config, preserve evidence under .runs/, update PLAN-0034/CURRENT.md and write a new handoff.
```
