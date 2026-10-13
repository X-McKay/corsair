---
id: PLAN-0076
kind: plan
title: Local Corsair results interface
status: complete
updated: 2026-10-13
related: [SPEC-0069, SPEC-0044, IDEA-0009]
---

# Local Corsair results interface

## Objective and dependencies

Implement SPEC-0069 in managed worktree corsair-ui on branch codex/corsair-ui, starting from main e760f05. User authorized parallel development and selected inspection of existing results. Reference source: infosec-harness UI at 52aa2ac. No existing Corsair web API; use a narrow local read-only projection over current evidence formats.

## Steps

- [x] Build bounded read-only API and static server; validate filesystem and HTTP boundaries.
- [x] Adapt frontend presentation with real Corsair evaluation/runtime contracts and provenance.
- [x] Wire Make commands, documentation and CI checks.
- [x] Validate browser behavior and visual quality against real local API; run affected offline suite.
- [x] Review, resolve findings, update current index and handoff.

## Validation and progress

Initial inspection: harness UI has routes backed by Temporal/API contracts that Corsair does not implement. Selected patterns and helpers will be adapted instead of exposing unsupported actions. Backend and frontend agents work in parallel with an explicit JSON contract; root owns integration and browser validation. No live model or sandbox calls authorized by or necessary for this scope.

## Decisions and next action

Keep React/TypeScript/Vite for familiar frontend development and use stdlib Python HTTP for local inspection only. Avoid another router/query framework unless needed. Do not implement IDEA-0008 release gates or change agent/evaluation semantics. Implemented the read-only UI, native-sample metrics, reference neutral/violet styling, loopback API and CI. Ready for PR review; no production deployment or model/sandbox qualification.


Final implementation evidence (2026-10-13):

- Two implementation subagents owned API and frontend independently; root owned integration, metrics view, browser validation and records. Backend also reviewed frontend metric claims.
- API boundary: 37 focused tests passed. Native per-attempt metrics preserve0 and omit live tokens without explicit usage coverage; cohorts hash recorded identities and isolate missing identities. Caps500summaries/100reports/20k samples are reported.
- Frontend: production TypeScript/Vite build and9 unit tests passed; selected helpers and contrast audit retain upstream attribution. No remote assets or telemetry.
- Browser:34passed,5 intentionally skipped duplicate mobile contrast checks. Real local API and production assets exercised in desktop/dark/mobile projects. First contrast harness invocation incorrectly passed a page wrapper to page.evaluate (10failures); corrected harness exposed3light-theme sidebar count contrast failures, fixed and rerun green. A real dark-theme inherited text/background issue was caught visually and fixed. No failures hidden.
- Existing scripted identification eval generated16/16clean attempts; observed in UI with actual native-token/latency distributions. These are scripted fixtures, not live performance/accuracy. Screenshot retained locally outside Git.
- Dev server API proxy health smoke passed after explicit target Host rewrite; production listener remains same-origin loopback only.
- Initial full make test-config:1782passed in108.58s. Final expanded suite result recorded in publication handoff. No live inference, Temporal server or sandbox workloads launched.

The user explicitly expanded scope to aggregate/per-agent metrics and distributions, and requested the reference app aesthetic. Both are included. The read-only launch restriction remains.
