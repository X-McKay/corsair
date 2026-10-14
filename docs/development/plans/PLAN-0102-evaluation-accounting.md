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

## Post-publication concurrency refresh

PR #174 was refreshed onto be80d47c609c70307cf39308ad1da12ebcc62459 after upstream D18 implementation and six licensed imported JavaScript cases landed. The only manual conflict was CURRENT.md; preserve chain 106 and the upstream records. This PR does not take credit for that native implementation/corpus. Refreshed focused/post-cleanup tests: 21 passed; full serial and four-worker suites: 1688 passed, 113 skipped (138.04s / 52.17s). All seven scripted evaluators passed; chain now has 106 clean attempts; no baseline promoted. Earlier bdb evidence remains private history.

## Final delivery concurrency update

All four PRs are **draft/open**: [#174 — evaluation accounting](https://github.com/X-McKay/corsair/pull/174), [#175 — CLI/lifecycle](https://github.com/X-McKay/corsair/pull/175), [#176 — developer skills](https://github.com/X-McKay/corsair/pull/176), [#178 — audit/roadmap](https://github.com/X-McKay/corsair/pull/178). None was merged by this task.

After initial publication, develop added D18 execution, six imported JavaScript cases, four imported Ruby cases and Investigator repetition/validation changes. These are upstream improvements, not this audit patch. PR #174 alone was refreshed onto `92278eeddcf325104346c5f397f28f37476a2b9e`; its CURRENT.md row was placed below the stable index rather than rewriting changing corpus counts. Its final snapshot checks: **122 focused passed**, **1702 passed/113 skipped** in both full topologies and **14 post-cleanup passed**. The earlier 1688-case and bdb tables are historical. No model prompt or baseline was promoted by this task, and no native/live accuracy is inferred from these tests.

The source ZIP is explicitly the **reviewed bdbb2a91 combined integration snapshot**, with all three originally validated audit code areas and final documentation, not a claim to be the continually advancing develop head or the newly rebased #174 head. It passed **1658 tests/113 skips** in both topologies and **128 post-cleanup tests**. Current individual PRs are the preferred source for independent review; the private bundle preserves all snapshot identities and measured/failed attempts. Native workspace/model benchmark accuracy and complete pipeline token/latency trade-offs remain unqualified here.
