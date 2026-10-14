---
id: PLAN-0105
kind: plan
title: Port the results UI (PR #107) to v2
status: implemented
updated: 2026-10-14
related: [SPEC-0084, HANDOFF-0139]
---

# Port the results UI (PR #107) to v2

## Objective and dependencies

SPEC-0084. Base: develop af6ff16 (after #193 package move and #195). #107 (`codex/corsair-ui`, base main 2a3dcb2, v1) is superseded: its UI subtree was carried onto a fresh branch from develop instead of rebasing ~30 v1 merge commits whose code no longer exists.

## Steps

- [x] Carry `ui/`, `src/corsair/web/`, `deploy/ui/`, the UI workflow and runbook onto develop.
- [x] Server: v2 run records, eval summaries, policy, reference, baselines, chain-attempt records, v2 matrix.
- [x] Services: `corsair.v2.Investigation` visibility with record links; OpenShell probe without v1 adapters.
- [x] Pages: Overview, Runs + Run detail, Evaluations + detail with comparison, Agents, Runtime matrix, System.
- [x] Tests: `tests/ui` (API, services, renderer, real producer), Playwright over real scripted output.
- [x] Image, renderer and smoke on the v2 layout; `ui` dependency group without the agent stack.

## Validation and progress

2026-10-14, cloud container, no model, no Docker:

- `make eval AGENT=<each of the six agents and chain>`: all scripted runs clean (chain 132/132); used as live-shaped local data.
- `uv run --locked python -m pytest tests/ui`: 57 passed.
- `npm test` 7 passed; `npm run build` (tsc + vite) clean.
- `npm run test:e2e` with Chromium 1194 via `CORSAIR_UI_CHROMIUM`: 38 passed, 7 skipped (mobile contrast by design).
- Real Temporal: `temporalio.testing.WorkflowEnvironment.start_local()` (CLI 1.9.1, server 1.32.0), a started `corsair.v2.Investigation` with id `corsair-v2-<run id>` was listed by `/api/workflows` with its record link; namespace probe `available`.
- Not run here: the production image build and `deploy/ui/smoke.py` (no Docker in this container; CI runs them), `make test-v2` full suite result is in the PR checks.

## Decisions and next action

Next: CI green on the PR, then merge to develop per the merge-on-green policy. A live deployment, live OpenShell probe and live-run rendering remain unqualified until someone runs them.
