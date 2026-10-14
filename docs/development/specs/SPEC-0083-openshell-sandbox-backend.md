---
id: SPEC-0083
kind: spec
title: OpenShell backend for the v2 sandbox port
status: accepted
updated: 2026-10-14
related: [SPEC-0082, PLAN-0100, HANDOFF-0136]
---

# OpenShell backend for the v2 sandbox port

## Goal and scope

Al, 2026-10-14 10:34Z: OpenShell must be fully functional before develop replaces v1. SPEC-0082 already names OpenShell as the second implementation of the workspace interface. This spec makes it real for every place v2 executes untrusted code: the Builder agent's workspace, trusted build replay, probe execution (including the D3 check run) and the reconciler. Docker stays the default and keeps its exact behaviour. Out of scope: the kind/OpenShell milestone gate itself (PLAN-0100 sequences it), held-out scoring, row upgrades to `live`, and narrowing build egress per matrix row.

## Boundaries and design

- **One port for trusted code.** `src/corsair/v2/workspace/port.py` defines `Sandboxes`: `create` (never adopts; a held identity is `SandboxExists`, neither reused nor removed), `copy_tree_in`, `write_file`, `copy_out`, `exec_once` (once, never retried; timeout and lost sandbox are facts), `drop_network`, `image_id`, `resolve_image`, `remove` (True only when absence is confirmed), `labelled`, and the environment trio `find_environment` / `seal_environment` / `open_environment`, plus `agent_workspace`, which returns the native PydanticAI `WorkspaceBackend`. `build.py`, `execute.py`, `reconcile.py` and `chain.agent_workspace` call only the port. No language knowledge enters it.
- **Explicit selection.** `workspace.sandboxes()` reads `CORSAIR_WORKSPACE` (`docker` when unset, or `openshell` with `CORSAIR_OPENSHELL_CONFIG`). Any other value, or `openshell` without its config, is an error. There is no fallback between backends.
- **Docker** (`DockerSandboxes`) wraps the existing helpers. An environment is a committed image labelled with its key and build-log digest. A recording fake `docker` CLI showed byte-identical docker argv before and after the refactor for replay (with and without setup network), `run_probe`, `diagnose` and the sweep.
- **OpenShell** (`OpenShellSandboxes`, `OpenShellWorkspace`) uses the native SDK 0.1.3 for lifecycle, exec and file transfer (a tar stream over exec stdin, in 1 MiB chunks, built from `lstat` so a symlink is a link entry and is never followed). It uses the pinned, hash-checked CLI only for `policy set --wait`, which the SDK lacks, and confirms that the requested document is loaded on the original sandbox id, as v1's SPEC-0006 gate did. Images come from the operator's digest-pinned map, and an unmapped image is an error. `remove` deletes by the recorded id and waits for NOT_FOUND. Anything uncertain is `cleanup_unconfirmed`.
- **Environments on OpenShell.** OpenShell cannot snapshot a sandbox. Replay still runs once and proves the baseline, then seals a manifest (key, log digest, recipe and its digest, tree path and digest, base image) under the operator's `state_dir`. Each probe's fresh sandbox replays that recipe on the runtime image (setup under the `build` policy only when the recipe asked for network, then the `none` policy) before the probe file is written. That costs one setup per probe and keeps "probes never run where an agent typed". The trade-off: a non-hermetic setup step could install something different between replay and probe. That shows up as a failed control, never as a silent pass.
- **Policies.** `policies/openshell/v2/none.yaml` grants no network. `build.yaml` adds GET-only egress on 443 to the union of the matrix's `build_network_hosts`, which narrows the egress Docker could not. Both are operator-owned and untrusted until the live policy gate passes.
- **Platform.** The kind/Calico/Agent Sandbox/gateway setup from the last pre-removal develop commit (9c3bc62) is restored unchanged in its pins and provenance rules. `tools/openshell_images.py` loads the matrix images into the node by verified manifest digest and writes the backend config. See [the runbook](../../runbooks/openshell-v2.md).

## Acceptance and validation

Implementation (offline, this PR): the full suite passes. It includes a host-double suite for the trusted call order over the port (`tests/v2/test_trusted_over_port.py`), 63 offline OpenShell adapter tests against an SDK/CLI double, and offline guards for the restored setup and image loader. Live qualification (not yet run): `make qualify-openshell-v2` passes PydanticAI's `WorkspaceBackendSuite` against `OpenShellWorkspace` and the shared `Sandboxes` port suite against the live gateway, with Docker passing the same port suite. Then one decisive case runs end to end on OpenShell with the same verdict, terminal reason and per-probe outcomes as on Docker, and confirmed cleanup. Until both hold, OpenShell is implemented, not qualified.

## Decisions and open questions

Open facts only a live gateway settles are listed in HANDOFF-0136: Landlock on a not-yet-existing `/work`, the exec user, the stdin limit, 124 timing, the `policy get` JSON keys, the image field in `sandbox get`, build-policy binary paths and TLS for each registry client, name and selector acceptance, and the resource-limit shape.
