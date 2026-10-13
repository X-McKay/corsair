---
id: PLAN-0072
kind: plan
title: Configurable inference and ticket providers
status: complete
updated: 2026-10-13
related: [SPEC-0066]
---

# Configurable inference and ticket providers

## Objective and dependencies

Implement SPEC-0066 on main 6d99d66 in an isolated worktree. Preserve the primary checkout and existing vLLM callers.

## Steps

- [x] Add model configurations and per-agent resolution using native providers.
- [x] Wire isolated/direct/durable evaluation entry points and resolved evidence.
- [x] Add ticket port, GitHub/Azure adapters and capture CLI.
- [x] Test negative paths, document configuration, review and hand off.

## Validation and progress

Read pinned PydanticAI 2.55.0 provider source and upstream documentation. Existing configuration only admits vLLM; chain already accepts distinct stage model instances and durable model keys. GitHub and Azure issue capture are absent. No live inference or credentialed ticket requests dispatched.

## Decisions and next action

Named model profiles are selected per agent with an explicit default; overrides reference complete profiles so credentials/settings from different providers never accidentally mix. Ticket provider selection is independent. Retain existing local config files via an explicit compatibility loader.


## Delivered and reviewed

Implemented named vLLM, OpenAI-compatible and native Bedrock Converse profiles with independent selections for all six agent keys, an optional explicit default, and legacy-file support. Isolated, direct and durable entry points resolve the same complete profiles; credentials remain operator-owned. GitHub/Azure capture returns vendor-neutral snapshots with bounded pagination, a private-file CLI and an explicit identification-input bridge. Added config examples and the provider configuration runbook. No agent prompts, tools, output contracts or sandbox policy changed.

Merged current main bb4f3b7 (including the planning package split) into the worktree without conflicts. Renumbered initial SPEC-0065/PLAN-0071 to SPEC-0066/PLAN-0072 after PR #89 independently published those identifiers. Final review using corsair-review corrected sparse live-stage CLI validation and an OpenAI-only metadata assumption that would crash Bedrock evaluations. Bedrock metadata now reads native botocore retry settings; absent retry telemetry stays unknown.

## Actual checks and retained attempts

- Isolated `uv sync --locked` succeeded; native PydanticAI remains pinned at 2.55.0, adding its Bedrock extra and locked AWS dependencies. The first lock attempt could not write the default cache; the isolated cache resolved that. A sandboxed uv test attempt failed DNS while revalidating the existing OpenShell dependency; no tests ran. A sandboxed async test run was interrupted before usable results; host checks below replace it.
- First targeted host tests: 39 passed, 2 failed due to test expectations for reverse client cleanup and native Converse's empty system field; both corrected. Expanded target: 97 passed, 1 failed due to treating native usage as a method; corrected. An overlapping full run collected the old usage assertion: 1514 passed, 1 failed. Dedicated new adapter/provider checks then passed 27/27.
- After merging bb4f3b7, `UV_CACHE_DIR=/tmp/corsair-provider-uv-cache make test-config`: 1522 passed in 87.84 seconds (`/tmp/provider-final-checks.log`).
- `make eval AGENT=planning`: 12/12 clean scripted attempts, zero task failures. Evidence `.runs/evals/planning/20261013T135746Z-development-scripted/`. `make eval AGENT=chain`: 5/5 clean scripted attempts, zero task failures. Evidence `.runs/evals/chain/20261013T135817Z-fixture-scripted/`. No earlier same-mode run in this worktree; no baseline promoted.
- Sparse-profile CLI regression and corrected record IDs: targeted checks 54 passed. Initial invocation named a nonexistent test path and ran no tests; corrected to `test_fixture_composition.py`. Initial helper edit used unavailable `python`; rerun with `.venv/bin/python` before changes were applied.
- Bedrock metadata review checks: 106 passed, 2 failed because the newly expanded test assumed a default botocore total retry count; fixtures now explicitly configure one total attempt, matching production client construction. Final full suite: **1523 passed in 87.58 seconds**, `/tmp/provider-reviewed-full-checks.log`. Example configuration validation and ticket CLI help also passed without opening clients.

## Qualification limits and next gate

HTTP mock transports, Bedrock Stubber, scripted agent evaluations and offline durable composition checks are not live service qualification. No authenticated ticket reads, hosted model spend, native Temporal service, or OpenShell gate ran. Supply an authorized model/identity and read-only ticket target for bounded live checks, then evaluate each selected agent/profile before promoting a baseline. Existing full real-case environment-chain integration remains separate work. Raw evidence remains ignored/local.

## PR 91 integration follow-up — 2026-10-13

Merged main `164a556` into the provider branch from `1e184bc`. Resolved the two fixture-chain conflicts by retaining per-agent model dispatch/profile metadata and main's canonical identification import and four-field version identity including `toolset_sha256`. PR #95 remains open and its local-vLLM limits are not part of this merge; if it lands first, carry those changes into `inference/vllm.py` while retaining the compatibility shim.

`UV_CACHE_DIR=/tmp/corsair-provider-uv-cache make test-config`: **1646 passed in 90.27 seconds**. `make eval AGENT=chain`: **5/5 clean scripted attempts**, zero task failures, matching the previous 5/5 run. Local evidence: `.runs/evals/chain/20261013T143851Z-fixture-scripted/`. Inspected configuration output: all four stages retain toolset digests and stage provider metadata remains present. Initial inspection used an incorrect shallow glob and found no configuration; corrected with recursive lookup. Merge whitespace check reports one pre-existing trailing blank line from main in PLAN-0070, outside this correction. No live provider, authenticated ticket, native Temporal or OpenShell qualification was run.

## Review corrections — 2026-10-13

Integrated main `1c6d26a` (including #95 and #92) from PR head `4c09082`. Kept the legacy provider shim and moved #95's 24576/32768 response caps and 300-second timeout to `inference/vllm.py`; aligned OpenAI-compatible and Bedrock timeout bounds to 300 seconds. Credential references are now provider-specific literals, rejecting ticket/ambient names before client creation. Ticket-to-agent text is JSON with format labels and excludes discussion by default; explicit inclusion preserves comment IDs/authors/timestamps and labels participants as unverified. This does not sanitize evaluation oracles out of descriptions; corpus admission must still curate agent-visible input.

Also reject GitHub dot segments, compare two bounded Azure discussion reads to detect edits without work-item revision changes, and release failed capture reservations after identity checking. Double reads are not a transactional snapshot. No `record-numbers.md` exists in this checkout or the primary repository; existing records and CURRENT remain the canonical index, so no speculative duplicate registry was introduced.

Validation: `UV_CACHE_DIR=/tmp/corsair-provider-uv-cache make test-config`: **1659 passed in 91.05 seconds**, also recorded in HANDOFF-0093. An initial un-escalated targeted run stalled after two tests and was interrupted; the full host run supersedes it. No live providers, authenticated service calls, native Temporal or OpenShell qualification ran.
