---
id: HANDOFF-0001
kind: handoff
title: Development workflow and platform continuation
status: recorded
updated: 2026-10-10
related: [SPEC-0002, PLAN-0002, PLAN-0001, ISSUE-0001, ISSUE-0002]
---

# Development workflow and platform continuation

## Verified state

Branch: `main`. Base revision for this work: `047e0bf5dac888f0bbe64c03e24a3e9e09b66397`. The workflow and this handoff are being committed together; inspect `git log`/`git status` to resolve the published revision and any subsequent changes. The user authorized shared Codex/Claude development skills and standard repository work tracking; existing repository publication authorization continues to apply.

Three canonical skills, shared instructions, five templates, current-work records, a PR template and offline workflow guards are implemented. Existing system architecture and runtime code remain unchanged. The runtime's first platform/CNI subset remains implemented but unqualified; OpenShell/Agent Sandbox, adapters, Temporal and agents are pending.

## Validation and blockers

`make test-config`: ten checks pass, including existing guards and new skill/record/link/CI invariants; all ten also pass from a fresh staged-index checkout with preserved symlinks and no ignored state. [PLAN-0002](../plans/PLAN-0002-development-workflow.md) records review and actual validation. Native Codex 0.159.2 metadata discovery could not initialize on this read-only client state environment, including a retry with documented local SQLite/log paths; both failed attempts remain in `.runs/development-discovery/`. Claude is unavailable. [ISSUE-0002](../issues/ISSUE-0002-native-client-discovery.md) tracks client smoke coverage. Hosted CI is unobserved at handoff creation.

Existing platform evidence is in the [qualification report](../../qualification/network-platform.md); the owned failed cluster was cleaned up. [ISSUE-0001](../issues/ISSUE-0001-nested-container-runtime.md) remains open for missing real kernel-device/nested overlay prerequisites. No provider/model calls or live runtime qualification are part of this workflow change.

## Decisions and next steps

Use native skills and Markdown records, not a tracker service or duplicated tool-specific rules. Keep one bounded component active, preserve evidence and reuse the existing accepted design. The next runtime step is the same platform suite on a compatible Linux Docker host, followed by a second clean creation/run. Do not connect OpenShell while that prerequisite is blocked; independent supported-host research, offline fixes and client skill smoke checks can proceed.

## Continuation prompt

```text
Continue Corsair from the repository. Read AGENTS.md and docs/development/CURRENT.md, then HANDOFF-0001, PLAN-0001, SPEC-0001 and ISSUE-0001. Inspect git/source state and the reviewed platform qualification report; verify facts rather than assuming the handoff is proof. Use the Corsair development skill.

The current milestone is native platform/CNI qualification. On a compatible Linux amd64 Docker host, run make tools, make test-config, make kind-up, make qualify-network with a new evidence directory, and make kind-down. Preserve every attempt and require confirmed cleanup. After a passing run, repeat from a second clean cluster. If host/runtime prerequisites still fail, retain their native diagnostics, keep the plan blocked and issue open, and continue useful independent work; do not weaken policies, fake kernel facilities or silently substitute a runtime.

Only after this gate passes should work proceed to selecting pinned Agent Sandbox/OpenShell artifacts and actual kernel/storage/gateway qualification. Use the existing OpenShell milestone plan. Review changes, record actual validation/coverage, update the plan/issue/CURRENT.md, and write the next numbered handoff before ending substantial work.
```
