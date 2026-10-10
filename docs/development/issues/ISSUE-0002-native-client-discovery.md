---
id: ISSUE-0002
kind: issue
title: Native client skill discovery smoke check
status: open
updated: 2026-10-10
related: [SPEC-0002, PLAN-0002, HANDOFF-0001]
---

# Native client skill discovery smoke check

## Observed and expected behavior

The checked-in skill layouts, frontmatter and symlinks pass offline guards. Installed Codex CLI 0.159.2 cannot initialize its stdio metadata server in this environment's read-only client state directory. Claude CLI is unavailable. Expected: fresh compatible clients list all three enabled repository skills and load the shared instructions. This is a client/environment coverage gap, not evidence of malformed skills or runtime failure.

## Reproduction and evidence

`codex --version` reports 0.159.2. `codex app-server --stdio -c analytics.enabled=false` exits before its initialize response because SQLite state under the configured client home is read-only. A second attempt supplies documented `sqlite_home` and `log_dir` paths under `.runs/development-discovery/`, and still exits with a read-only filesystem error. Neither attempt sends a model turn. Private stderr references: `.runs/development-discovery/codex-app-server.stderr` and `attempt-02.stderr`.

## Attempts and diagnosis

Protocol schemas were generated with the native CLI; the intended metadata request is `skills/list` with repository cwd and `forceReload: true`. The code never reaches that response. No global client state permissions or `CODEX_HOME` variables were changed. Structural discovery-path checks remain useful but cannot stand in for an actual client response.

## Resolution criteria and next action

In a fresh Codex session with normal writable client state, confirm exactly the three `corsair-*` skills at repository scope. In Claude Code, confirm `/corsair-development`, `/corsair-review`, `/corsair-handoff` and the `@AGENTS.md` import. Record the client versions, actual results and remaining limitations before resolving. Instruction compliance needs task-specific review/evaluation beyond discovery. This issue does not block the separate platform work or delivery of the shared workflow files.
