---
id: HANDOFF-0048
kind: handoff
title: Local model response cap raised to 16384
status: recorded
updated: 2026-10-12
related: [PLAN-0030, ISSUE-0007]
---

# Local model response cap raised to 16384

## Verified state

Branch `claude/raise-response-token-cap-ou7fqq` (PR #29) from main `83dec61`; resolve its published head with git. `LocalModelConfig` now accepts `response_token_limit` 16384 and `timeout_seconds` up to 240 s; defaults (2048, 60 s) and the separate thinking budget (at most 2048) are unchanged. The issue-analysis live CLI offers 16384 and a `--timeout-seconds` option. No contract, authority, retry, policy or pin changed. Per-agent cap selections are recorded in PLAN-0030 and belong on each agent's branch.

## Validation and blockers

`make test-config`: 394 passed. Live on RIG0 against llm.almckay.io, no retries, private evidence `.runs/token-cap-20261012/` on RIG0: one full 16384-token response took 125.94 s (about 130 tokens/s); evidence-assessment cases b and c at 16384/180 s cut cap failures from 3/7 to 1/6 with admitted results unchanged at 2; issue identification stayed 16/16 with its largest response at 1283 tokens. Full tables are in [PLAN-0030](../plans/PLAN-0030-response-token-cap.md). Six assessment attempts are a smoke, not qualification. The identification eval's 180 s task deadline equals the 180 s client timeout used; that overlap was not exercised. Two RIG0 worktrees remain under `.runs/token-cap-20261012/wt/` for removal with `git worktree remove`.

## Decisions and next steps

The user approved raising the cap. A larger cap removes truncation but not semantic defects: every case-c completion proposes a verified fix that the gate rejects, and the remaining case-b failure spent its budget alternating between readings. Those belong to the evidence-assessment prompt and evals work on PR #25. PR #26 and PR #28 move the provider module behind a re-export shim; whichever merges after this PR keeps the shim and applies the `Literal` and `le=240` changes to `src/corsair/agents/provider.py`.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then PLAN-0030, ISSUE-0007 and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. If PR #26 or #28 has merged, reconcile the provider move as described here and rerun make test-config. For agents that select 16384, also select a client timeout above 126 s and keep task deadlines longer than the client timeout. Do not treat the higher cap as a semantic fix; evidence-assessment verified-fix proposals remain its own prompt/evals work. Update work records/CURRENT.md and write a new handoff.
```
