---
id: PLAN-0028
kind: plan
title: Environment agent and sandbox source fetch implementation
status: blocked
updated: 2026-10-12
related: [SPEC-0029, SPEC-0025, SPEC-0026, IDEA-0004, ISSUE-0006, PLAN-0021]
---

# Environment agent and sandbox source fetch implementation

## Objective and dependencies

Implement [SPEC-0029](../specs/SPEC-0029-environment-agent.md): the isolated environment agent and the offline contracts of [SPEC-0025](../specs/SPEC-0025-sandbox-source-fetch.md) (source fetch) and [SPEC-0026](../specs/SPEC-0026-sandbox-dependency-fetch.md) (phase policies, realized dependency inventory), with deterministic tests only. Live use is blocked: SPEC-0025 names a qualified quota-enforcing storage volume as an admission blocker, and private repositories also need the OpenShell 0.1.3 credential placeholder behavior confirmed. [ISSUE-0006](../issues/ISSUE-0006-native-transfer-retry-admission.md) stays open for general transfers. No durable stage is connected.

## Steps

- [x] Deterministic fetch node `corsair.nodes.source_fetch`: fixed recipe script, URL/commit/credential-binding validation, strict receipt parser, host admission against `SourceSnapshot`, single dispatch through `SandboxExecution`.
- [x] `corsair.nodes.phase_policy`: three ordered revisions (repository host for git's HTTPS helper only; GET-only registries per ecosystem, refused for private source and for ecosystems without inventory coverage; no network).
- [x] `corsair.nodes.dependency_inventory`: strict realized-inventory parser with operator generated-file lists and replay drift comparison.
- [x] Environment agent: contracts, `prepare-environment` skill, stage-owned toolset, trusted output function, scripted tests.
- [x] Align ready output with the planner's `EnvironmentEvidence` fields (framework, baseline test path, language, runtime) as pushed on the test-planning branch.
- [ ] Per-ecosystem operator inventory scripts (Python `pip inspect` plus `RECORD` hashing; Maven local repository) and their local tests.
- [ ] Policy-control adapter: load a revision with `policy set --wait`, observe the loaded revision and a native denial event.
- [ ] Setup-replay node: replay the recipe in a fresh sandbox through the three phases and compare realized inventories.
- [ ] Live qualification of SPEC-0025 and SPEC-0026 once a quota-enforcing storage volume is qualified; confirm the credential placeholder in 0.1.3 before any private repository.
- [ ] Live-model evaluation of the agent against a qualified preparation sandbox; durable activity design; composition into `EnvironmentEvidence`.

## Validation and progress

2026-10-12: `make test-config` passed with the results recorded in [HANDOFF-0046](../handoffs/HANDOFF-0046-environment-agent-and-source-fetch.md) (baseline on main `83dec61` was 390 passed). Node tests: 124 (`tests/unit/test_source_fetch.py`, `test_phase_policy.py`, `test_dependency_inventory.py`); agent tests: 48 (`tests/agents/test_environment.py`). Each agent refusal case was checked to fail on its intended trusted-check message rather than incidentally.

The local fetch test runs with local Git 2.43: a bare repository is captured with the real `GitSource`, fetched shallowly from `file://` by the test (the production script refuses `file://`), then the fixed materialize and inventory script parts run. Files with `eol=crlf` and `ident` attributes materialize byte-identical to their blobs (a normal clone of the same repository does transform them), and a modified, added, deleted or mode-changed file, an empty directory or a symlink is refused. `FETCH_SCRIPT` itself refuses `file://`, a non-empty workdir (exit 65), and symlink or submodule tree entries before writing.

Unrun and not claimed: any OpenShell, provider or Temporal run; whether OpenShell 0.1.3 accepts the `/**/git-upload-pack` rule glob; whether toolchain images provide the script's tools (`git`, `git-remote-https`, GNU `stat -c`, `xargs -0`, `base64`, `printenv`, `sort`, `od`); whether the proxy resolves a basic-auth placeholder; storage bounds.

## Decisions and next action

- The fetch command is `(shell, -euc, FETCH_SCRIPT, corsair-source-fetch, shell, git, workdir, url, commit, placeholder-variable-name)`; data travels only as positional arguments. The script is assembled from fixed parts so tests can run the materialize and inventory parts without a protocol bypass.
- Script refusals exit 65 (`source_admission`) or 66 (`credential`, placeholder absent); any other nonzero exit is `dependency`, per SPEC-0025.
- The secret check runs before every other receipt check, including on an `ExecutionError` receipt, so leaked output is always attributed to `credential`. Only raw secret values are matched.
- The placeholder is passed as `-c http.extraHeader=...` and is visible in the sandbox process list; only the placeholder, never the token, appears there.
- The network grant names git's HTTPS remote helper (`git-remote-https`), the binary that opens connections, not `git`.
- Directory entries are compared as an exact set without mode, since their mode depends on umask.
- The agent's model never authors dependency digests; read and budget refusals return `ToolFailed` so the model can report blocked; commands are argument vectors with the sandbox as the boundary.
- Next action: per-ecosystem inventory scripts and the policy-control adapter can proceed offline; live steps wait on the storage volume.
