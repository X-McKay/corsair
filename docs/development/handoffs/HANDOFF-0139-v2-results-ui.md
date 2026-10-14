---
id: HANDOFF-0139
kind: handoff
title: Results UI ported to v2
status: recorded
updated: 2026-10-14
related: [SPEC-0084, PLAN-0105]
---

# Results UI ported to v2

## Verified state

Branch `claude/project-thread-jmaqx8` from develop af6ff16. Supersedes PR #107 (v1). The UI reads v2 run records, eval runs, baselines, the v2 matrix, Temporal `corsair.v2.Investigation` visibility and OpenShell health; it writes nothing.

## Validation and blockers

See PLAN-0105 for commands and results: tests/ui 57 passed, UI unit 7 passed, Playwright 38 passed over real scripted chain/reviewer output, real local Temporal listing verified. Docker image build and smoke run in CI only. No live deployment.

## Decisions and next steps

Merge on green. Afterwards close #107 as superseded (Al's call). Once live baselines land, the Agents page shows them without change; per-attempt latency/token histograms could return then.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then SPEC-0084, PLAN-0105 and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. Run `make ui-install ui-build ui` against real .runs output and fix any rendering gap for live records (provider errors, OpenShell image digests, cancelled runs). Run tests/ui, make ui-check and make ui-test, update the records and write a new handoff.
```
