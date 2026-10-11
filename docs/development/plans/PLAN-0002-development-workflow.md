---
id: PLAN-0002
kind: plan
title: Shared development workflow
status: complete
updated: 2026-10-11
related: [SPEC-0002, HANDOFF-0001, HANDOFF-0002, HANDOFF-0004, PLAN-0001, ISSUE-0002]
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

During the final required-section guard edit, pytest collection failed on an unterminated string; that local edit was corrected before the final rerun. Review: one canonical skill set, native instruction/discovery conventions, no new dependencies or runtime services, existing system design retained, and live qualification claims unchanged. Local structural checks are not model-compliance or runtime evidence.

The first [hosted run](https://github.com/X-McKay/corsair/actions/runs/38082789713) passed all ten tests on Python 3.12.3, then failed setup-uv's post-job cache step: its configured cache directory was absent because Make unconditionally replaced `UV_CACHE_DIR`. The fix makes that assignment a default (`?=`), preserving supplied SDK/CI configuration while retaining the writable local default. A native Make/uv cache probe returns the explicitly supplied path; `make test-config` still passes all ten after the correction. This is a cache integration correction, not a test or runtime-boundary failure. Subsequent hosted results are available in the native [workflow history](https://github.com/X-McKay/corsair/actions/workflows/development.yml); preserve the failed run rather than relabeling it passed.

## Decisions and next action

Use the already-present pytest/PyYAML stack for a small set of offline guardrails. These detect structural drift; they are not an agent compliance evaluator or runtime admission. The scoped workflow deliverables are complete; native client smoke coverage remains open. [PLAN-0001](PLAN-0001-local-platform-qualification.md) is now complete on the qualified host tuple; actual OpenShell installation, storage and kernel/runtime admission remain the next live gate.
