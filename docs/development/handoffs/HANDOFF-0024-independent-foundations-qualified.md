---
id: HANDOFF-0024
kind: handoff
title: Independent Temporal and PydanticAI fixture foundations
status: recorded
updated: 2026-10-11
related: [PLAN-0015, SPEC-0013, PLAN-0016, SPEC-0014, PLAN-0013, ISSUE-0006, HANDOFF-0023]
---

# Independent Temporal and PydanticAI fixture foundations

## Verified state

Resumed HANDOFF-0023 under explicit user authorization to use Sol sub-agents, research primary documentation and periodically commit/push progress. Two Sol agents implemented independent components; a third reviewed current OpenShell capability and both foundations. Root owned shared pins, installation, cross-component checks, raw audits, records and publication. No deployment, merge, external issue closure or upstream messaging occurred.

Branch `codex/parallel-foundations`, stacked draft [PR17](https://github.com/X-McKay/corsair/pull/17) above `codex/openshell-untrusted-output`/PR16. Base handoff checkpoint `d49ad72c0c623f9b156254adad3ae2fedd125461` was committed/pushed first; its exact-head [CI38199558859](https://github.com/X-McKay/corsair/actions/runs/38199558859) succeeded. Foundation code checkpoint `f78b96d517061a1426083b80181eaae95cebf542` is pushed and PR17 attached. This document follows in a separate records checkpoint; resolve its final SHA through Git rather than assuming the code checkpoint contains it. Exact code-checkpoint [CI38200233882](https://github.com/X-McKay/corsair/actions/runs/38200233882) completed successfully; its actual job log records182 passed, one warning /7.17s. The subsequent records checkpoint still needs its own exact-head CI verification; no future status is invented.

Delivered independently:

- [Temporal SPEC-0013](../specs/SPEC-0013-temporal-fixture-foundation.md) / [PLAN-0015](../plans/PLAN-0015-temporal-fixture-foundation.md): plain typed fixture payloads, one native parent/child workflow, preparation and completion activities, explicit bounded retry ownership, native cancellation, real history export/replay and a separate-process persistent-service restart probe. [Report](../../qualification/temporal-fixture-foundation.md), [runbook](../../runbooks/temporal-fixture.md).
- [PydanticAI SPEC-0014](../specs/SPEC-0014-issue-analysis-template.md) / [PLAN-0016](../plans/PLAN-0016-issue-analysis-template.md): one explicit instrumented agent factory, saved in-memory source authority, read-only source tool, typed hypothesis/missing-facts output, scope/exact-quotation/current-run-read admission, native usage limits and local deterministic Evals. No finding/fix verdict. [Report](../../qualification/issue-analysis-fixture.md).
- Shared exact Python tuple: Temporal1.34.0, PydanticAI slim[temporal]2.55.0, Evals[logfire]2.55.0. All pre-existing non-project lock records, including OpenShell's 12-package closure, are unchanged. Native integration imports pass, but metadata/import compatibility is not durable-agent qualification. Current new APIs use `Instrumentation` and `TemporalDurability` capabilities; deprecated `TemporalAgent` was not introduced.
- Temporal CLI1.9.1/embedded service1.32.0 Linux amd64 acquisition is pinned in `deploy/temporal/runtime-lock.yaml`. Root verified the official archive checksum before extracting the exact binary; runtime reverified its hash. Newest standalone service1.32.1 is a different tuple and was not silently substituted.

OpenShell's previous two-node fixed untrusted-file qualification was re-audited successfully from raw evidence before dependency edits. OpenShell0.1.3 and Agent Sandbox1.0.6 remain the latest stable releases in the fresh primary-source review. There was no new OpenShell live matrix this session. The historical 72-input freeze remains historical: expanded `pyproject.toml`/`uv.lock` are new inputs for any future live candidate, even though existing package records are unchanged. ISSUE-0006/general transfer and reconciliation remain blocked.

## Validation and blockers

Private evidence root: `.runs/parallel-foundations-20261011/`, with root, temporal-agent, pydantic-agent and openshell-agent ownership. Never commit this tree, `.state/`, `.tools/`, credentials, SQLite files, raw histories or logs.

| Boundary | Actual result |
| --- | --- |
| Resume baseline | `UV_OFFLINE=true make test-config`: 148 passed / 4.58s before new dependencies; prior paired OpenShell raw audit exit0 |
| Expanded lock during concurrent docs | 147 passed / one broken-link failure because Temporal report had not yet been written; retained root/expanded-lock-baseline.log |
| Final combined offline suite | `UV_OFFLINE=true make test-config`: 182 passed / 5.03s, one native run_sync event-loop deprecation warning; includes old guards, 26 agent and eight Temporal offline checks |
| Final affected checks | Explicit repository cache, offline pytest development-record plus Temporal-contract files: 12 passed / 0.14s |
| Temporal native004 | 14 passed / 3.407s JUnit, zero skips/failures: eight offline plus six real service cases; separate checkpoint prepare0.314s/resume0.414s across same-SQLite graceful service restart |
| PydanticAI | 26 isolated checks / 0.35s; evaluation003 six scripted runs, 30 assertions, zero task/evaluator errors, ten responses, four source reads, six trace IDs; estimated984 input/528 output tokens, summed task0.056071858s |
| Handoff record checks | Offline development-record checks: four passed /0.03s after the new handoff/current/plan update |
| Independent review | Cross-run citation reuse reproduced and fixed using native run IDs; original parent/child identity binding and evidence overwrite prevention added; root and sibling raw audits passed |

Temporal's preserved native004 freeze has 13 inputs, manifest SHA256 `36d1d59074a4146ba005cef942780cfd4ce4880fc5d5190816dd74d64dc0a1c1`. Seven actual parent/child pairs preserve immutable run links; fourteen final histories replayed (12 Completed, two Cancelled). Original persistent parent `01a12e29-7e2e-7f39-bcec-8ec8f3a73114` and child `01a12e29-7e61-79a1-9c7a-f0b6661852ae` histories retain their pre-restart prefixes; one preparation and one completion occurred. Original service PIDs669873/start49542108 and670298/start49542658 were reaped exit0, absent, and ports17333/17334/17336 closed. No service remains running. Final staged review removed one trailing blank line in `tests/temporal/support.py`; that sole frozen-input difference is documented as whitespace only, without claiming a new live run.

Pydantic source-v2 freezes and retains copies of11 inputs including shared locks; manifest SHA256 `61c0ab763ff817e9de6fa3cd8e579a43d84da721ec0c0a9c630a837df7c55ff6`. Oracles remain evaluator-owned outside stage inputs. Scripted outputs and estimated tokens prove contract plumbing, not model reasoning, prompt-injection resistance, provider billing or production latency. Missing native agent spans are an explicit negative control.

Failures remain attributable: initial restricted DNS/socket preparation refusals; stale Pydantic constructor/Dataset/usage assumptions; interrupted synchronous-callback attempt with unconfirmed cause; Temporal native001's completed operation followed by an untyped reconnected-client assertion failure; earlier successful candidates superseded by review. Plans/reports retain each attempt, correction and original cleanup. No possible external side effect was blindly replayed. Root's failed multi-file documentation patch made no change; staged whitespace review caught/fixed one previously untracked EOF blank line. No policy, TLS, kernel or budget was weakened.

Unqualified: real providers/semantic analysis, native durable agent composition, supported Temporal tracing, process crashes during activities/lost completion, actual external unknown dispatch, resource cleanup, production service/TLS/auth/database, cross-version replay and complete investigation graph. Native restart was graceful, cancellation occurred at a waiting barrier and unknown delivery was simulated. The bounded component plans are complete; neither full Milestone3 nor5 is complete.

## Decisions and next steps

1. Verify PR17's exact current head/base/CI and this records checkpoint's publication. Do not merge stacked PRs without authorization. Current authorization continues tested commits/pushes and Sol sub-agent development; it does not authorize external messages or issue closure.
2. Next independent composition candidate: exercise the same issue-analysis factory/contracts in native `PydanticAIWorkflow` with `TemporalDurability`/`PydanticAIPlugin`, using explicit fixture models and local supported telemetry. First read selected-version source/docs, update a focused plan, then compare direct/durable contracts, limits, tool authority, replay and metrics. Do not wrap a whole agent in a generic retryable activity. No provider or OpenShell connection is implied.
3. Alternatively/alongside that independent candidate, the smallest reviewed OpenShell evidence extension is fresh-process receipt observation after the existing actual EACCES result-storage failure and original sandbox cleanup. Extend the existing `test_adapter_execution_storage_failure.py`; use its saved intent/identity and absence of result, without passing the parent process's in-memory terminal receipt to the reader. A worker-loss persisted-result control should remain. This is proposed only; no production reader/reconciliation API was added or qualified. Freeze current complete inputs and use two fresh mandatory-admitted nodes for a live claim.
4. Native exec_stream offers no qualified remote-process cancellation receipt; closing a generator/SDK or a local timeout does not establish remote termination. Agent Sandbox signalling is a different unqualified transport, not a fallback. A report consumer still needs an approved concrete schema; keep the fixed opaque-file recipe narrow.
5. Keep default native readiness300s as an API wait, not an invented latency SLO. Existing OpenShell execution/storage/kernel/policy/TLS limits remain intact. Never infer full qualification from installed versions, imports, rendered config or fixture results.

## Continuation prompt

```text
Read AGENTS.md, README.md, docs/development/CURRENT.md, HANDOFF-0024 and the linked plans/specs/reports/issues using the Corsair development/review/handoff skills. Inspect branch/status/source and verify PR17's published head/CI plus actual frozen evidence; a handoff is context, not proof. Continue one bounded native component, with Sol sub-agents for independent work/review and root ownership of shared pins/Git/runtime resources. Prefer the documented same-factory direct/durable fixture composition or the proposed fresh-process OpenShell receipt observation; update its focused plan before editing. Research primary selected-version documentation, use supported native APIs and preserve simplicity. Run smallest offline checks before live work, retain failures and original identity cleanup, preserve all integration gates, update records/reports, review final diff and append a handoff. Periodically commit/push only authorized tracked changes; never include private runs/state/credentials/raw logs. No deployment, merge, issue closure or external messaging is authorized.
```
