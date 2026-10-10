---
id: SPEC-0002
kind: spec
title: Shared development workflow
status: accepted
updated: 2026-10-10
related: [PLAN-0002, HANDOFF-0001, ISSUE-0002]
---

# Shared development workflow

## Goal and scope

Provide a repeatable repository-based development process across Codex and Claude sessions, as requested by the user. Standardize principles, current work, ideas, specs, plans, development issues, reviews and continuation prompts. Avoid a custom tracker/service or duplicated tool-specific rules.

## Boundaries and design

`AGENTS.md` is the shared rulebook; Claude imports it via `CLAUDE.md`. Three canonical skills live under `.claude/skills/`; Codex's supported symlink discovery exposes the same folders under `.agents/skills/`. Native Markdown/YAML-frontmatter records, templates, a short current-work index, PR template and offline pytest/GitHub Actions guards provide structure. Existing architecture/evaluation/qualification documents stay authoritative.

## Acceptance and validation

- Both native discovery paths resolve to one copy of each valid skill; the Claude entry point imports the shared rules.
- Five record types have templates, stable IDs, status meanings, standard sections, valid references and seeded current work.
- Offline checks detect broken skills/links, malformed records, dangling IDs and unsafe CI configuration; existing guards still pass.
- A handoff identifies source state, actual validation, platform blocker and copyable continuation prompt.
- Runtime qualification is unchanged; no provider, deployment, external issue closure or agent call is introduced.

Native client discovery/invocation is a later client smoke check if the actual CLI is unavailable here. Structural checks establish layout, not model compliance. Hosted CI execution is reported separately from locally running the same command.

## Decisions and open questions

The user's current request authorizes this workflow; no additional confirmation ceremony is required. Keep requirements proportionate: small edits reuse existing records. A separate tracker database, generated duplicate skills, hooks that modify code, and automated agent delegation are unnecessary. [ISSUE-0002](../issues/ISSUE-0002-native-client-discovery.md) tracks the native client smoke check that this host cannot complete.
