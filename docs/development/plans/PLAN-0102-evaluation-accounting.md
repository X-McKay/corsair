---
id: PLAN-0102
kind: plan
title: Evaluation accounting and declared policy scope
status: complete
updated: 2026-10-14
related: [SPEC-0082]
---

# Evaluation accounting and declared policy scope

## Scope and boundaries

Distinguish task/evaluator completion from conditional semantic accuracy and respect declared release-policy set/mode. Preserve upstream wall_s/tokens/retries/parameter fields, frozen policies, datasets and deferred promotion behavior.

This independent draft PR is based on develop integration snapshot `bdbb2a91135f61bb33cd19ec3a4421cf284094f5`. Other audit changes live in separate PRs, not prerequisites of this branch. The central source-backed audit/HANDOFF-0137 will be delivered in a separate documentation PR; this branch carries its own scoped record and current-work entry.

## Implementation and validation

Implementation is copied from the independently reviewed, reconciled integration worktree; native Temporal fixtures and all seven scripted evaluators passed there, but that does not replace standalone validation. Run `uv sync --locked --group dev`, focused tests, four-worker/serial full suites, final cleanup and re-test. Record actual results below before delivery.

Unrun/unknown: production provider accuracy, Docker/kind/gateway policy and native platform qualification, true backend end-to-end dispositions and native Claude/Codex client compliance. No baselines/prompts are promoted and no production service is deployed.

## Next action

Complete standalone validation and publish this draft for independent review. Do not merge automatically. Preserve failed evidence and explicit unknowns; follow current gate/coordinator decisions for any later live run.

## Final standalone evidence

Final base: `bdbb2a91135f61bb33cd19ec3a4421cf284094f5`; upstream D18 and native live-baseline/commit helpers preserved. Earlier `06d4cbe` validation is retained privately as history. This PR does not implement D18 verdict logic or claim native end-to-end model quality.

- Focused tests: **20 passed**.
- `TEST_WORKERS=4 make test-v2`: **1637 passed, 113 skipped**.
- `TEST_WORKERS=0 make test-v2`: **1637 passed, 113 skipped**.
- Final `git diff --check`: passed; post-cleanup focused re-test: **20 passed**.
- All seven affected scripted evaluator commands passed; live-only policies not_applicable; no promoted baseline.

The 113 live/runtime/conditional skips are not qualified behavior. Docker/kind/gateway, production provider, true native disposition/held-out benchmarking and external cleanup remain unrun. Raw `.runs/`, `.state/`, private logs/credentials and weights are excluded from this PR.
