---
id: PLAN-0071
kind: plan
title: Configurable inference and ticket providers
status: in_progress
updated: 2026-10-13
related: [SPEC-0065]
---

# Configurable inference and ticket providers

## Objective and dependencies

Implement SPEC-0065 on main 6d99d66 in an isolated worktree. Preserve the primary checkout and existing vLLM callers.

## Steps

- [ ] Add model configurations and per-agent resolution using native providers.
- [ ] Wire isolated/direct/durable evaluation entry points and resolved evidence.
- [ ] Add ticket port, GitHub/Azure adapters and capture CLI.
- [ ] Test negative paths, document configuration, review and hand off.

## Validation and progress

Read pinned PydanticAI 2.55.0 provider source and upstream documentation. Existing configuration only admits vLLM; chain already accepts distinct stage model instances and durable model keys. GitHub and Azure issue capture are absent. No live inference or credentialed ticket requests dispatched.

## Decisions and next action

Named model profiles are selected per agent with an explicit default; overrides reference complete profiles so credentials/settings from different providers never accidentally mix. Ticket provider selection is independent. Retain existing local config files via an explicit compatibility loader.
