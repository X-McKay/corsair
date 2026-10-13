---
id: HANDOFF-0101
kind: handoff
title: Approved UI design implementation
status: recorded
updated: 2026-10-13
related: [SPEC-0069, PLAN-0076, HANDOFF-0100, IDEA-0009]
---

# Approved UI design implementation

## Verified state

Branch codex/corsair-ui in the managed corsair-ui worktree continues PR #107 from published5923b48. Main184e609 merged as65169e7 before final validation. Resolve the implementation revision from the commit containing this handoff and PR head; this document is committed with the changes. Primary-checkout unrelated edits were preserved.

User approved the mockups and requested one card per agent with stats and histogram frequency-line overlays. Implemented individual cohort-selectable agent cards, shared histogram scales and count-based curves, overview resource distributions with explicit mode selection, and saved-run experiment comparison. Neutral/violet light/dark appearance and responsive layouts retained. Comparisons require matching agent/set/provider mode/dataset and compatible recorded execution modes; show identity differences and incomplete measurements. No semantic accuracy score is invented. Total tokens combine input/output only within the same observed native attempt; missing telemetry stays unknown.

Server adds only paired total-token samples and SPA routes, and handles canceled browser responses. Inspection remains read-only, loopback-only, bounded and credential-free. Agent execution/evaluation contracts and policies are unchanged; no new dependencies.

## Validation and blockers

- make ui-build:17 UI unit tests and TypeScript/Vite production build passed.
- CORSAIR_UI_PYTHON=<worktree>/.venv/bin/python make ui-test:42passed,6 intentionally skipped duplicate mobile contrast checks in4.2s. Desktop/dark/mobile test real local API against synthetic saved fixtures, including populated comparisons and no horizontal overflow.
- UV_CACHE_DIR=/tmp/corsair-provider-uv-cache make test-config:1831passed in112.39s, including43 server boundary/metrics/cancellation tests, after merging current main.
- Review corrected native execution-mode versus wrapper provider-mode comparison. Initial browser failures and remediation retained in PLAN-0076. git diff --check passed before publication; development-workflow guards rerun after final record edits.
- Actual saved scripted identification report inspected in production preview:1run,16attempts and16native latency/token samples. This is fixture evidence, not live model accuracy. No live inference, Temporal server or OpenShell workload launched.
- Preview listens at127.0.0.1:8765 with updated production assets and backend; Ctrl-C stops it. Browser test servers use disposable roots and exit. Screenshots and logs remain local outside Git; no .runs/.state or raw private artifacts committed.

Remaining limits: only retained reports can be compared, unavailable failed-attempt telemetry stays explicit, recorded identities cannot prove every effective setting is known, and descriptive deltas do not establish causal improvement or held-out accuracy. PR CI/review remains the publication gate; no merge or deployment authorized.

## Decisions and next steps

Approved design is implemented. Update existing PR #107, inspect its CI and review. Keep job launch, baseline promotion, release policies and live evaluations outside this presentation change. Use a new handoff for subsequent work rather than editing this snapshot.

## Continuation prompt

```text
Read AGENTS.md, CURRENT.md, SPEC-0069, PLAN-0076 and HANDOFF-0101. Inspect codex/corsair-ui and PR #107 source/CI before trusting the recorded state. Use the Corsair development skill. Review the approved UI against real saved reports; make bounded requested revisions, preserving unknown telemetry, cohort boundaries and descriptive comparison limits. Run make ui-build ui-test and relevant server tests; run make test-config for backend contract changes. Update records and write a new handoff. Do not launch workloads, promote baselines or merge without authorization.
```
