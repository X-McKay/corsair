---
id: HANDOFF-0119
kind: handoff
title: Local results UI and agent metrics
status: recorded
updated: 2026-10-13
related: [SPEC-0077, PLAN-0091, SPEC-0044, IDEA-0009]
---

# Local results UI and agent metrics

## Verified state

Branch codex/corsair-ui starts from main e760f05 in the managed corsair-ui worktree. User requested a similar improved infosec-harness UI, parallel agents, a new worktree/branch and visual validation; explicitly selected inspection-only, then requested aggregate/per-agent metrics and reference aesthetics. Two agents implemented API/frontend, root integrated metrics, docs, CI and tests. Resolve final source from Git history.

Delivered: local loopback read-only server; overview, searchable evaluation list/detail, runtime evidence, per-agent recorded cohorts, aggregate activity counts, token totals and native-sample latency/token histograms. Native reports remain authoritative. No inferred general accuracy score: individual correctness assertions retain their names/denominators. Missing telemetry and scripted estimates are explicit; 0/0 is not success. Neutral/violet light/dark UI uses selected attributed upstream helpers. No launch/cancel/edit routes. Make targets and UI CI job added.

## Validation and blockers

- Final make test-config:1791passed in106.93s, including37backendHTTP/filesystem/metrics tests. Earlier base integration1782passed in108.58s.
- Frontend9unit tests, TypeScript production build and browser-test typecheck pass.
- Playwright34passed,5skipped duplicate mobile contrast checks, desktop/dark/mobile against real local API and synthetic saved evidence. Final run3.6s. Contrast/first harness failures and fixes retained in PLAN-0091.
- Scripted identification host eval16/16clean attempts generated local real report, verified in browser including16 native latency/token samples. No live model or sandbox qualification. Test fixtures remain distinct from this saved run.
- Vite dev proxy GET/api/health passed. Screenshots inspected in light/dark/mobile; actual metrics screenshot stays outside Git. git diff --check passed.
- Production preview runs at127.0.0.1:8765 for local inspection; Ctrl-C stops it. Ignored .runs and dist remain local. Browser test servers use temporary roots and stop after tests.

Limits: no live investigation service or job control; only saved wrapper eval results (including chain) and checked-in runtime matrix. Files/sample caps and unavailable failure telemetry are surfaced. Cohort identity reflects recorded settings, not proof every effective configuration is known. This is not a public/authenticated multi-user service. No provider credentials, raw inputs, transcripts or arbitrary artifacts exposed.

## Decisions and next steps

Implementation complete within accepted read-only scope. Review the PR and CI; no UI merge or deployment was requested. Future execution controls need a separate authorized execution boundary. Keep IDEA-0008 release policy deferred and preserve CLI/evaluator semantics. Existing primary-checkout edits were not changed by this body of work.

## Continuation prompt

Read AGENTS.md, CURRENT.md, SPEC-0077 and PLAN-0091, verify branch/source and PR status. Use make ui-install ui-build ui to inspect local saved evaluations. For changes run targeted API/frontend tests and make ui-test, preserve unknowns/evidence scopes, and avoid exposing raw reports or adding silent model/workload execution. Update records and retain failure history.
