---
id: PLAN-0022
kind: plan
title: Native feature adoption from the repository review
status: in_progress
updated: 2026-10-12
related: [IDEA-0002, ISSUE-0006, ISSUE-0007, SPEC-0010, SPEC-0015, SPEC-0016]
---

# Native feature adoption from the repository review

## Objective and dependencies

Implement the offline-verifiable items of [IDEA-0002](../ideas/IDEA-0002-simplification-isolation-and-generality-review.md) sections C and H: use PydanticAI, Temporal and OpenShell features the repository re-implemented or left unused, close the two security-scope gaps (fixture label in the prompt; invented tool calls retried), and make operator budgets and usage accounting explicit. Three file-disjoint work packages were implemented by delegated agents in isolated worktrees and merged; the root reviewer verified the upstream facts against the installed packages before delegation and reviewed the merged diff.

Items that need a fresh admitted node or a live Temporal service are excluded and listed under next actions: gateway metrics snapshots, `configuration_admission.config_revision` polling, structured global-policy listing, the policy prover guard, `request_id` reconciliation, chart value migration, and offline replay of committed histories. ISSUE-0006 and ISSUE-0007 remain the gates they were.

## Steps

- [x] PydanticAI package: `retries={"tools": 0, "output": n}`; `fixture_prompt` excludes `fixture_id`; `VLLMProvider` with explicit `server` selection and model-level `ModelSettings`; instrumentation version pinned; `path` parameter described; output validator counts only `outcome == "success"` reads; `unsupported` may carry no missing facts; evaluation metadata derived from one frozen configuration; `run_id`, `output_corrections` and `unknown_tool_attempts` recorded; `NoUnknownToolAttempts` evaluator.
- [x] Temporal package: single typed `IssueAnalysisRequest` with an `IssueAnalysisBudget` and operator ceiling; typed non-retryable `ApplicationError` refusals; `IssueAnalysisExecution` reports `usage_reported`, `None` tokens when unreported, `output_corrections`, `run_id`, `mode`, `elapsed_seconds`; explicit workflow, activity, signal and query names; `execution_timeout` and `memo` in native tests; sandbox import-notification policy.
- [x] OpenShell package: typed `GatewayError` details (`native_reason`, `native_domain`, `native_retry_delay`, `native_field_violations`) in both receipts; explicit `LifecycleLimits` passed to `wait_ready` and `wait_deleted` and journaled in the intent; `restart_policy` must be stated as NEVER; redundant empty-ID guard removed; `NATIVE_UNCERTAIN_EXITS` named.
- [x] Merge, run the offline suite on the combined branch, independent review against the review skill (no blocking code defects; stale record statements corrected in SPEC-0009, SPEC-0014, SPEC-0016, two runbooks, CURRENT.md and IDEA-0002), records, handoff.
- [ ] Re-record durable and OpenShell evidence on a live service and fresh admitted node. Every live slice built on `inert_spec`/`recovery_spec` now sends `SANDBOX_RESTART_POLICY_NEVER` instead of the unspecified value (lifecycle, recovery including OOM and gateway restart, adapter lifecycle/execution, source upload/execution, execution artifacts/receipts/transport, untrusted file, test report), so each needs a fresh run; renamed workflows and activities do not replay old histories; lifecycle timeouts are now explicit at the previous values.

## Validation and progress

Offline, on the merged branch at the published head: `make test-config` passed 286 checks (baseline before the change: 255). Each package passed the same suite in its worktree before merging (269, 261 and 266). `.venv/bin/python -m pytest tests/temporal -q` reports the native tests skipped without `--temporal-address`; `pytest tests/qualification --collect-only` collects the live modules. The fixture evaluation CLI ran with exit 0 and its metadata now comes from the configuration object. New tests were contrast-checked against the previous source by the implementers: the invented-tool refusal, the `fixture_id` exclusion, the tool-schema description, the failed-read filter, the `unsupported` rule, the lifecycle timeouts, the restart-policy refusal and the structured error fields all fail on the old code.

Unrun: every live qualification test under `tests/qualification` and `tests/temporal/*_native.py`. Nothing in this plan is live-qualified. Known consequences for later live runs: histories recorded under the old workflow and activity names will not replay against this code; the live spec now sends `SANDBOX_RESTART_POLICY_NEVER` where it previously sent the unspecified value; `PROMPT_VERSION` was `issue-analysis-fixture-v5` because the rendered prompt and tool schema changed, with instructions text unchanged; after merging main's skill/toolset/output-function work it is `issue-analysis-numbered-source-v2` (main's v1 plus the fixture-id exclusion, the `path` description and the relaxed `unsupported` status description), and main's thinking controls and response cap are typed `LocalModelConfig` fields in the one model-level settings mapping; evaluation report metadata keys changed shape, so comparisons with earlier reports need a mapping.

## Decisions and next action

Decided: `InlineDefsJsonSchemaTransformer` stays an explicit override because `VLLMProvider` supplies it only for some model families; the implementer's mock-transport probe found request bytes unchanged. `usage_reported` is derived from `result.new_messages()`. The model-key admission check against the durability registry lives in the test support module because the capability exposes its registry privately. Fixture ids are excluded from the prompt but not renamed to opaque values (deferred; they remain in host-side receipt names). Bool and float budget values are refused in direct mode only; the durable payload converter coerces lax JSON before admission, and the ceiling remains the effective guard. The evaluation CLI needs `PYTHONPATH=src:.` outside pytest, as PLAN-0016 recorded. The tool retry budget of zero means an invented tool ends the run; such attempts are counted in the attempt receipt, and the evaluator only confirms the count for completed cases.

Next bounded action: on a fresh admitted node and an operator-owned Temporal service, re-run the issue-analysis durable composition and the OpenShell adapter slices with this code, then update the qualification reports. Then take IDEA-0002 package 1 (policy profiles with a typed loader, lock pin and prover guard). Stop condition: any live failure attributable to the explicit restart policy or lifecycle timeouts reopens this plan.
