---
id: PLAN-0002
kind: plan
title: Shared development workflow
status: complete
updated: 2026-10-10
related: [SPEC-0002, HANDOFF-0001, PLAN-0001, ISSUE-0002]
---

# Shared development workflow

## Objective and dependencies

Implement [SPEC-0002](../specs/SPEC-0002-development-workflow.md) without adding runtime infrastructure, duplicated skills or a tracker database. This can proceed independently of the platform blocker. Preserve the existing architecture and qualification limits.

## Steps

- [x] Confirm native skill format/discovery; select one canonical copy and shared instructions.
- [x] Add development/review/handoff skills, record templates and process guide.
- [x] Index the current platform plan/blocker and a deferred idea using standard records.
- [x] Add the native PR template and pinned-action offline development workflow.
- [x] Run structural/record/link and existing checks; review actual coverage.
- [x] Record results, update current work and handoff; deliver these files together in the authorized repository commit.

## Validation and progress

`make test-config`: ten checks pass (the original six plus four skill/record/link/CI checks). A fresh checkout of the staged Git index also passes all ten with its own environment and no ignored local state; the Codex discovery symlinks survive that checkout. Native Codex symlink discovery is documented upstream; its installed CLI is 0.159.2. An initial stdio app-server metadata probe fails on its read-only SQLite state directory. A second probe uses the documented `sqlite_home`/`log_dir` overrides in `.runs/`, without changing `CODEX_HOME`, and still exits with a read-only filesystem error before initialization. Both stderr logs are retained in `.runs/development-discovery/`; no model turn is dispatched. Claude is not installed. [ISSUE-0002](../issues/ISSUE-0002-native-client-discovery.md) tracks the remaining native client smoke check, outside this file/structural-delivery scope.

During the final required-section guard edit, pytest collection failed on an unterminated string; that local edit was corrected before the final rerun. Review: one canonical skill set, native instruction/discovery conventions, no new dependencies or runtime services, existing system design retained, and live qualification claims unchanged. Hosted GitHub Actions execution is observed separately after publication; local structural checks are not model-compliance or runtime evidence.

## Decisions and next action

Use the already-present pytest/PyYAML stack for a small set of offline guardrails. These detect structural drift; they are not an agent compliance evaluator or runtime admission. The scoped workflow deliverables are complete; native client smoke coverage remains open and the platform plan remains blocked. Resume runtime qualification only on a compatible host.
