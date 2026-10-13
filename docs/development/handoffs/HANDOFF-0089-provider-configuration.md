---
id: HANDOFF-0089
kind: handoff
title: Per-agent inference and ticket source adapters
status: recorded
updated: 2026-10-13
related: [SPEC-0066, PLAN-0072]
---

# Per-agent inference and ticket source adapters

## Verified state

Implementation is on `codex/provider-ticket-adapters` in `/tmp/corsair-provider-tickets`, based on 6d99d66 with main bb4f3b7 merged. The original `/home/al/git/corsair` checkout and its unrelated dirty files were preserved. Resolve the published revision with `git log`/the PR head; this handoff is committed with the final changes.

All six agent keys can select an independent complete provider/model profile; an optional explicit default preserves convenient shared selection. Native PydanticAI vLLM/OpenAI Chat Completions/Bedrock Converse implementations own inference translation. Legacy local-vLLM files and imports remain supported. Isolated and direct/durable chain callers use resolved models and record selected profile/native model metadata. Unknown choices/missing configured API keys fail before model dispatch; no error fallback exists.

GitHub issue and Azure DevOps Services work-item adapters implement a narrow snapshot port. Capture is read-only, bounded, paginated, records revisions/observations, refuses incomplete captures and creates an exclusive private file. An explicit bridge builds the existing identification input using operator-supplied scope/source. Ticket text never chooses repository, scope, provider or policy. See `docs/runbooks/provider-configuration.md` and `config/examples/providers.json`.

## Validation and blockers

PLAN-0072 records commands, failed attempts, final fixes and actual results. The post-main-merge full offline suite passed 1522 tests; scripted planning passed 12/12 attempts and chain passed 5/5, with zero task failures. Final review corrected sparse live-stage CLI admission and Bedrock metadata retry inspection; the final full rerun passed **1523 tests in 87.58 seconds**. Example config validation and ticket CLI help passed without opening clients. Private evidence/logs remain local/ignored; no credentials or raw evidence are published.

Native provider request tests use HTTP mock transport or Bedrock Stubber, not live endpoints. Authenticated GitHub/Azure reads, live Bedrock/OpenAI-compatible agent behavior, native Temporal service and OpenShell execution were unrun. Full real-case environment-agent composition remains outside this implementation. These are qualification limits, not claims of success.

## Decisions and next steps

User authorized both adapters and clarified per-agent provider/model selection. No new approval is needed for this implementation/review. Publish the bounded implementation for review; do not merge or launch paid/cloud workloads on inferred targets. Review chosen endpoints, identities, models and read targets before bounded live qualification, then evaluate each agent/profile and compare frozen baselines. No baseline was promoted. SPEC/PLAN IDs were moved to 0066/0072 because PR #89 claimed 0065/0071 during development.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, SPEC-0066, PLAN-0072 and HANDOFF-0089. Inspect the PR head and worktree status; verify recorded facts against source and logs. Use the Corsair development skill. Review or address concrete feedback on provider/ticket adapters, preserving per-agent complete profiles, explicit selection, narrow snapshots and credential boundaries. Run make test-config and relevant native SDK/offline negative-path tests. Live qualification needs an authorized model/identity and read-only ticket target; do not label mocks or scripted evals as live qualification. Update work records/CURRENT and add a new handoff for substantial follow-up.
```
