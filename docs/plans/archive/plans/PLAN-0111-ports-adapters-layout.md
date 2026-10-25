---
id: PLAN-0111
kind: plan
title: Navigable ports and adapters package layout
status: implemented
updated: 2026-10-25
related: [PLAN-0110, ISSUE-0009, HANDOFF-0142]
---

> Historical record. Commands, counts and status describe the recorded revision, not the current working tree. See [current work](../../README.md) for current guidance.

# Navigable ports and adapters package layout

User requests agents/, ports/, adapters/, entrypoints/, policies/, workflows/, observability/, steps/, and considers evaluation/ and contracts/. Implement this organization with actual existing behavior, not provider placeholders. Preserve all prior uncommitted qualification work and main stash; remain on manus/just with no publication unless authorized.

Move native SDK integrations into adapters; CLI/worker/programmatic API into entrypoints; domain orchestration into steps and pure decisions into policies; evaluation out of observability; contracts split by real domain dependency. Add narrow typed inference/SCM/sandbox ports used by actual consumers, with domain-only inputs/outputs. Reuse native Google ADK/Temporal/Docker SDKs. Existing local source snapshots are the sole SCM implementation; native ADK/LiteLlm and Gemini are the inference integration. GitHub/AzureDevOps checkout and Bedrock-specific integration are documented extension points, not fake implementation files. No HTTP server/deployment or new credentials are introduced.

Preserve console behavior and wire contracts through canonical contracts exports; change the installed script entrypoint, package resource locators, driver build path and all live imports/tests together. Remove retired source modules instead of carrying compatibility shims. Historical work records retain original commands. Verify full Ruff/ty, installed wheel outside checkout, native Mac Docker/Temporal/replay/CLI and isolated model evals, then any admitted live composition. Keep failing attempts and semantic eval failures explicit. No freeze hashes, security policies, runtime budgets or labels are changed to obtain passes.


## Completion and actual results

Implemented locally on manus/just. Native ADK output_schema/Pydantic replaced custom producer completion; the requested ports/adapters/contracts/evaluation organization is functional, not scaffolding. Strict Ruff/format/Just-format/ty pass. Complete physical-Mac suite with real Docker, Temporal and live auditor:134 passed in139.71s; final installed-wheel recheck1 passed in7.74s, sdist/wheel build succeeded. Frozen producer3/3; auditor6/6. Frozen request/oracle/source hashes, budgets and SDK/Nix locks unchanged. Full live model/worker/native batch2/3: original/fixed and conditional cases passed, safe follow-up probe retained ERROR/INCONCLUSIVE under ISSUE-0010. No hidden policy weakening or passing-live-accuracy claim. Linux current-local-revision CI remains unrun. See HANDOFF-0143 for commands, private evidence, exact cleanup and preserved local state. No commit/push/deployment performed.
