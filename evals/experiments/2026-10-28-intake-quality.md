# Intake quality diagnostic, 2026-10-28

Status: authored candidate diagnostic, not a promoted baseline. Implementation and exact commands are recorded in [PLAN-0134](../../docs/plans/active/PLAN-0134-intake-quality.md). [ISSUE-0015](../../docs/plans/active/ISSUE-0015-intake-v3-live-quality.md) remains open.

## Frozen boundary

Eight cases from `evals/datasets/intake-capabilities.json`; unchanged input/source/inventory hashes, external labels, native schema bytes, scoring, model and budgets. Model: `openai/Qwen3.6-35B-A3B-NVFP4`, native LiteLLM/OpenAI-compatible route at the operator-authorized endpoint. Episodes: 60 seconds, sequential requests. Labels/oracles remained evaluator-owned. Costs remain unknown.

The control imported source/resources extracted from the prior built wheel. Source/resource bytes matched the prechange tree. The structure variant added native JSON MIME and a single canonical input packet with explicit complete preloads, plus truncation handling and content-free validation diagnostics. The final variant additionally clarified issue normalization, scope, surface/mode/capability categories and available-image matching. Neither introduced repairs, recipes, new permissions or target execution in intake.

| Variant | Attempts | Exact | Correct decisions | Invalid outputs | Model failures | False-supported |
| --- | --- | --- | --- | --- | --- | --- |
| Fresh control | 8 | 0 | 3 | 2 | 1 | 0 |
| Structure only | 8 | 1 | 3 | 3 | 0 | 0 |
| Final guidance, repeat one | 8 | 6 | 8 | 0 | 0 | 0 |
| Final guidance, repeat two | 8 | 8 | 8 | 0 | 0 | 0 |

Final exact total: 14/16; decisions: 16/16, including both missing-context abstentions. Supported recall: 6/6 on this cohort. Remaining exact mismatches: one surface label and one out-of-scope execution-mode label. Classification agreement across repeats does not establish agreement for every field. The earlier 1/8 exact intake run remains retained, not replaced by this fresh control.

Resource identities:

- Control: `7ba73b93fc7243ba70050ba20b52e1c8cf9234d5fb31e03975c5b6d53f059c2e`.
- Structure: `689b645f25a7b05848a26ac2172b9bff5a6d118023efa95ce156fc02955c60ed`.
- Final: `4623709f565e67b469c0926827c3b5567f0450d3f97e501232a0f7f15883c3d2`.

Settings digest was identical: `f74593b812bfba726f3407f60f0dd6d7e15388a8e7df16f4dbf6d72ae9a59342`. Private reports and immutable artifacts remain under `.runs/intake-improvement-20261028`; no raw model reasoning or private evidence is published here.

## Native checks and limits

The final offline suite passed **322 tests, 81 deselected**, including genuine scripted ADK and installed-wheel resources outside checkout. Real Docker/Temporal/replay passed **11 tests, 1 live test deselected**. Pinned quality checks and wheel/sdist build passed; the build retained the existing uv version-range warning. Distributions contain no private/cache paths, and wheel source/resource bytes match the final tree.

The model diagnostic uses genuine ADK and real read-only inspection Docker with frozen hypothetical inventories. It does not test physical image admission, generated test execution, full model-chain success or vulnerability accuracy. The small authored cohort is pending human review; repeated familiar cases are not held-out data. Individual prompt rules were not causally isolated. Current-tree Linux/CI and broader human-labelled, family-grouped held-out repeats remain unrun. Producer/full-chain failures were not altered. No baseline was promoted and no changes were committed or pushed.
