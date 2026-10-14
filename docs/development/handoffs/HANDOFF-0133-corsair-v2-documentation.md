---
id: HANDOFF-0133
kind: handoff
title: Corsair v2 operator documentation checkpoint
status: recorded
updated: 2026-10-14
related: [SPEC-0082, PLAN-0097, ISSUE-0009]
---

# Corsair v2 operator documentation checkpoint

## Verified state

Branch `manus-test`; observed source/base revision `14715eab1ca4b9ff778636987601d48a443779cc`. Workspace already contains the v2 implementation and substantial changes from other work. This handoff records only the documentation lane; it does not claim a clean tree, commit, push, or implementation ownership. No production source file was edited here.

Updated/added v2 operator documentation, architecture/ADR records, and the active SPEC-0082 / PLAN-0097 / CURRENT summaries. Existing `docs/v2/metrics.md` was read for link/claim alignment and intentionally not modified. The parent owns live e2e test execution and will author `docs/v2/validation.md` with actual results; links are present, but this lane did not add a placeholder or invent validation counts.

The docs describe the CLI/library only (no web console), native PydanticAI/Harness, Temporal and Evals composition, and the OpenShell/storage/qualification boundaries. The local Docker OpenShell profile stays unqualified; the certificate is operator attestation, not a signed runtime certification. The store is local POSIX CAS + SQLite WAL within one execution domain, not PostgreSQL/S3/multi-host storage.

## Validation and blockers

Read-only commands actually run:

- `git branch --show-current` -> `manus-test`; `git rev-parse HEAD` -> `14715eab1ca4b9ff778636987601d48a443779cc`.
- `uv run --offline corsair-v2 --help`, `init --help`, `schema --help`, and command help for doctor/run/worker/submit/status/cancel/history/reconcile/analyze/eval/benchmark/compare/promote-baseline.
- `uv run --offline corsair-v2 schema operator --json`, `schema run --json`, and `schema source-analysis --json` (schema fields were inspected, no live service invoked).
- Read-only source inspection of actual contracts, agent factory, Temporal workflow/identity, SQLite WAL store, OpenShell qualification, docs, and upstream research files.
- Lightweight Markdown local-link/trailing-whitespace audit over the changed documentation and `git diff --check`: no broken local links apart from the intentionally parent-owned, not-yet-created `docs/v2/validation.md` target; no trailing whitespace; tracked diff whitespace check clean.

No provider, model, Temporal service, OpenShell gateway, or workload was invoked by this documentation task. This lane did not run an end-to-end suite or the repository-wide `make test-config`/record guard. Run those appropriate offline guards after the parent writes `validation.md`; the audit here is only a local link/whitespace pass. Do not use earlier exploratory model trials as final validation.

## Decisions and next steps

Keep the gateway as a registered native OpenShell gateway name, with CLI registration/auth context; do not document raw mTLS gateway URLs as Corsair config. The CLI accepts a `sandbox.cli_path` profile field even though `init` does not expose a `--cli-path` option. The CLI's init defaults are `qwen3:4b` plus `provider=ollama`; a local Qwen endpoint is not a semantic/tool quality guarantee.

Parent next step: complete the already-authorized live e2e checks against frozen logs/policy, write actual outcomes and boundary-specific caveats in `docs/v2/validation.md`, then run relevant repository documentation/record checks without modifying code frozen by the live test lane. Any unqualified OpenShell profile, unavailable provider/tool/typed output, or uncertain effect stays a blocker/refusal, not a pass or fallback.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then SPEC-0082, PLAN-0097, this handoff, and docs/v2/README.md. Inspect git/source state; verify the live test's frozen configuration, model, logs and target-host OpenShell evidence. Run only the already authorized v2 live validation. Record actual results and explicit failures/unknowns in docs/v2/validation.md; do not invent counts, convert exploratory runs to final claims, or edit production code while the parent e2e lane freezes it. Run the documentation/record checks appropriate to the finished docs and update PLAN-0097/CURRENT with exact outcomes. Keep Docker-profile qualification gated until the exact target host's OpenShell evidence admits it.
```
