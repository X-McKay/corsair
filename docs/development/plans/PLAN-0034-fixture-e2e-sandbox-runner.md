---
id: PLAN-0034
kind: plan
title: Fully live fixture E2E over the OpenShell test workspace
status: in_progress
updated: 2026-10-13
related: [SPEC-0031, SPEC-0032, PLAN-0031, PLAN-0032, SPEC-0025, PLAN-0028, ISSUE-0007]
---

# Fully live fixture E2E over the OpenShell test workspace

## Objective and dependencies

Close the open PLAN-0031 step: plug a `Runners` factory over the [SPEC-0032](../specs/SPEC-0032-openshell-test-workspace.md) OpenShell test workspace into the [SPEC-0031](../specs/SPEC-0031-fixture-direct-composition.md) E2E-0 chain and run the SPEC-0018 fixture pair fully live on RIG0 (kind, OpenShell 0.1.3, local model), so a live author's own tests execute inside a fresh sandbox. Also gather live facts on the two open sandbox gaps that block real repositories under [SPEC-0025](../specs/SPEC-0025-sandbox-source-fetch.md)/[PLAN-0028](PLAN-0028-environment-agent-and-source-fetch.md): a quota-enforcing storage volume and the 0.1.3 credential placeholder.

Out of scope, owned elsewhere: witness capture outside the test process (SPEC-0033/PLAN-0033, parallel thread), so every gate verdict stays at most `completed`/`inconclusive`/`not_verified`; agent prompt or budget changes (PLAN-0035, parallel thread); real repositories, the environment agent and durable mode.

## Steps

- [x] `evals/fixture_e2e/sandbox.py`: `sandbox_runners` (one fresh sandbox per runner call, variant per purpose as in the reviewed route) and `sandbox_case` (sandbox discovery argv, toolchain pytest version, declared identity from the image manifest, argv, hash-pinned wheels, policy file and limits; revision sources are the captured snapshot manifests).
- [x] `evals/fixture_e2e/run.py`: `record_run` shared by the reviewed CLI and the live gate; configuration records route, environment, identity and revision sources; scripted planning follows the case's discovery argv.
- [x] Offline tests `tests/agents/test_fixture_sandbox.py` over fake sandbox ports: full scripted chain with three fresh sandboxes; a model-authored test is delivered and run (the host route refuses it); configuration and journal evidence.
- [x] Live gate `tests/qualification/test_fixture_e2e.py`, marker `fixture_e2e`, target `make qualify-fixture-e2e`: an all-scripted control asserted strictly, then `CORSAIR_E2E_RUNS` live runs recorded but not asserted; every native run must confirm cleanup and leave no Sandbox resource.
- [ ] Fresh RIG0 runtime and live run: control plus live runs on llm.almckay.io.
- [x] Storage quota facts from read-only inspection and a throwaway plain pod (below).
- [x] Live gate `tests/qualification/test_credential_placeholder.py`, marker `credential_placeholder`, target `make qualify-credential-placeholder`: one provider holding a random fake credential via the pinned gRPC provider RPCs, attached at sandbox creation; an in-sandbox scan (`credential_scan.py`, given only prefix, length and digest) records the variable's form and fails on the raw value in any readable process environment or bounded file scan; sandbox and provider deleted with identity checks; evidence searched for the value. Egress substitution is not implemented: the pinned proto names `NetworkEndpoint.credential_binding` but not its semantics, YAML spelling or protocol requirements.
- [ ] Run the credential placeholder gate live.
- [ ] Review, CURRENT.md, HANDOFF-0052.

## Validation and progress

2026-10-13, cloud container from main `0d9bb5a`: `make test-config` 781 passed before the change, 784 after (3 new). `-m fixture_e2e --collect-only`: 1 selected. PR #33 offline-guards CI green on `57195e9`. With the credential gate: `make test-config` 786 passed (2 new scan unit tests); `-m credential_placeholder --collect-only` 1 selected. Unverified assumptions in that gate: provider type `generic` is accepted, the credential key becomes a same-named environment variable inherited by SDK exec, a provider attaches under the identity policy with no network policies, `DeleteProvider` succeeds after sandbox deletion; it uses the SDK's private `_stub` because the SDK exposes no provider methods.

2026-10-13, RIG0 fresh runtime (worktree at `0d9bb5a`, evidence `.runs/live-e2e-20261013/`, private): `make tools` 0 (57 s); no prior cluster (`kind-down` refused without an ownership receipt, a safe no-op); `make kind-up` 0 (137 s, Calico inside the 180 s check, no retry); `qualify-network` 3 passed (163 s); admission artifacts/install 0; `qualify-admission` 1 passed (99 s); `openshell-install` 0; toolchain images cached and loaded 0. No Sandbox CR or boundary pod before the gate.

**Storage facts (read-only inspection plus one throwaway plain pod; no OpenShell sandbox created).** The gateway runs `workspace_mode=shared`, `workspace_storage_class=standard`, `allow_driver_config=false`. Its Sandbox CR (from the PLAN-0032 run) has a `workspace` volume claim template, RWO, 2Gi, class `standard`, mounted at `/sandbox`; `/tmp` (where the test workspace lives) is the container root overlay; runtime/state/run mounts are memory emptyDirs without `sizeLimit`; the agent has cpu 1 / memory 512Mi and no ephemeral-storage limit. Class `standard` is `rancher.io/local-path` (hostPath directory, no expansion), so the 2Gi request is not enforced. The node `/var` is ext4 without `prjquota`/`usrquota` mount options; no XFS. The CRD pod template accepts `emptyDir.medium`/`sizeLimit`, but the gateway builds the CR and the only user hook, `--driver-config-json`, is disabled; whether 0.1.3 driver config could add volumes is untested. A plain pod with a 64Mi memory emptyDir (`corsair-python`, non-root, 512Mi): tmpfs `size=65536k`; a 100 MiB write failed at 64 MiB with in-sandbox `ENOSPC` at write time; 200,000 empty files cost about 650 B each against the pod memory cgroup; a 1.5M-file flood ended in a memcg OOM kill (exit 137, about 47 s) before inode exhaustion. So a memory-backed `sizeLimit` volume bounds bytes synchronously, and inodes only through the memory limit (attributed as an OOM, not `ENOSPC`). It is not yet reachable through the OpenShell gateway and is not qualified; SPEC-0025 stays blocked on storage. Namespace deleted and confirmed absent.

**Credential placeholder facts (static only).** The pinned 0.1.3 CLI has `provider create|get|list|update|delete|refresh|profile|list-profiles` (`--credential KEY[=VALUE]`, `--runtime-credentials`), `sandbox create --provider` (repeatable; help says sandbox commands do not receive the real values) and `--no-auto-providers`; the binary names policy options `credential_binding`, `websocket-credential-rewrite`, `request-body-credential-rewrite` and `allow-uninspected-credentials`. Not observed: the in-sandbox value form and host-bound substitution. An ad hoc live probe needs a client TLS export outside the gate fixtures, which the RIG0 session's permission classifier refused; it was not worked around. The classifier also refused `make qualify-fixture-e2e` itself before anything ran (no evidence directory, no sandbox); it waits on the owner's permission.

## Decisions and next action

The sandbox route reuses PLAN-0032's adapters and wiring unchanged; the only new code is the purpose-to-variant factory, the sandbox environment declaration and the gate. The scripted control runs first in every gate invocation so a live failure can be attributed to the agent rather than the route. Live agent outcomes are not gate assertions. Next: switch the RIG0 worktree to this branch and run the gate.
