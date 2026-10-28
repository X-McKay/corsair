# Scanner JSON robustness diagnostic, 2026-10-28

Status: authored candidate evaluation, not a promoted or held-out baseline. See [PLAN-0135](../../docs/plans/active/PLAN-0135-intake-json-robustness.md) for implementation, exact commands, review and retained setup failures. The [original eight-case cohort](../datasets/intake-capabilities.json) was not edited.

## Boundary

The [new 32-case corpus](../datasets/intake-json.json), revision 2, exercises scanner-shaped SARIF, Semgrep, Bandit, GitLab SAST, Checkov and Trivy reports plus GitHub/Jira, rich text, envelopes, arrays, key/value records, strings, Unicode, noise, hostile metadata, duplicate/conflicting reports, missing context and absent images. Source includes a function finding, configuration and a synthetic dependency advisory. These are illustrative synthetic excerpts with synthetic identifiers, not actual scanner exports, scanner execution, complete versioned schemas or independent vulnerability families. Primary scanner format references are linked in the plan.

The runtime variant only clarifies finding/cardinality, metadata/image authority, path grounding and category guidance. Native canonical schemas, provider/model, permissions, inventories, cases, oracles, scoring and budgets remained unchanged between revision-2 baseline and candidate. Genuine ADK used `openai/Qwen3.6-35B-A3B-NVFP4` through the operator-selected endpoint, with real read-only inspection Docker and frozen hypothetical inventories. Calls ran sequentially with 60-second episode ceilings. These inventories do not prove physical image admission. Oracles and evaluation metadata were never passed to the agent. Costs remain unknown.

## Complete results

Correct decisions include expected `needs_input` results. Every planned attempt, invalid output and model/operational failure remains in the denominator.

| Run | Attempts | Exact | Correct decisions | False-supported | Invalid outputs | Model/operational failures |
| --- | --- | --- | --- | --- | --- | --- |
| Revision-2 baseline | 64 | 38 | 48 | 4 | 0 | 3 |
| Revised guidance | 64 | 39 | 52 | 2 | 0 | 3 |
| Original cohort, revised guidance | 8 | 6 | 8 | 0 | 0 | 0 |

Baseline repeat exact scores: 20/32 and 18/32. Normalization-detail checks: 44/48 planned relevant attempts, including failures. These are exact supplied-title and case-insensitive literal-fragment checks, not complete semantic fidelity.

Revised repeat exact scores: 23/32 and 16/32. Normalization-detail checks: 45/48 planned relevant attempts, including failures. These are exact supplied-title and case-insensitive literal-fragment checks, not complete semantic fidelity.

## Per-format results

Each row contains two attempts. Correct decisions and exact matching are separate so harmless category variation and material admission mistakes remain visible.

| Format/control | Baseline exact | Revised exact | Revised correct decisions | Revised false-supported |
| --- | --- | --- | --- | --- |
| canonical | 2/2 | 2/2 | 2/2 | 0 |
| github | 2/2 | 2/2 | 2/2 | 0 |
| jira | 2/2 | 2/2 | 2/2 | 0 |
| jira-rich-text | 1/2 | 2/2 | 2/2 | 0 |
| nested-envelope | 0/2 | 1/2 | 2/2 | 0 |
| singleton-array | 1/2 | 0/2 | 1/2 | 0 |
| findings-array | 2/2 | 1/2 | 2/2 | 0 |
| sarif | 1/2 | 2/2 | 2/2 | 0 |
| key-value-array | 1/2 | 1/2 | 2/2 | 0 |
| section-array | 2/2 | 1/2 | 2/2 | 0 |
| text-string | 2/2 | 1/2 | 1/2 | 0 |
| encoded-object-string | 2/2 | 1/2 | 1/2 | 0 |
| unicode | 1/2 | 2/2 | 2/2 | 0 |
| noisy-metadata | 2/2 | 1/2 | 1/2 | 0 |
| instruction-injection | 1/2 | 0/2 | 1/2 | 0 |
| repeated-equivalent | 1/2 | 2/2 | 2/2 | 0 |
| multiple-distinct | 0/2 | 2/2 | 2/2 | 0 |
| conflicting-reports | 0/2 | 0/2 | 0/2 | 2 |
| null-report | 2/2 | 2/2 | 2/2 | 0 |
| empty-array | 2/2 | 0/2 | 1/2 | 0 |
| numeric-scalar | 2/2 | 0/2 | 2/2 | 0 |
| title-only | 0/2 | 1/2 | 1/2 | 0 |
| absent-image | 2/2 | 2/2 | 2/2 | 0 |
| deep-envelope | 1/2 | 2/2 | 2/2 | 0 |
| semgrep | 0/2 | 1/2 | 2/2 | 0 |
| bandit | 1/2 | 1/2 | 2/2 | 0 |
| gitlab-sast | 2/2 | 1/2 | 1/2 | 0 |
| checkov | 0/2 | 1/2 | 2/2 | 0 |
| trivy-dependency | 1/2 | 1/2 | 1/2 | 0 |
| scanner-empty-results | 1/2 | 0/2 | 1/2 | 0 |
| sarif-two-results | 0/2 | 2/2 | 2/2 | 0 |
| scanner-noise-envelope | 1/2 | 2/2 | 2/2 | 0 |

## Provenance and native gates

- Baseline resource identity: `4623709f565e67b469c0926827c3b5567f0450d3f97e501232a0f7f15883c3d2`.
- Revised resource identity: `bcd299da5c5fc5f07edf43812c68a575b77e8f7be1106f7ad29d3fd40fb4d4ea`.
- Dataset revision-2 digest: `4c819a87a84caabadc877a0c5f28e2ae37ed74e1e5077350aeba5b7b8a270e39`.
- Evaluator source digest: `10a401f6ce4c03514383bef6d34b4d55c67edbdc7374df7769988c39f849ba88`.

All candidate input/source/inventory/settings digests and episode ceilings were checked against the baseline. The original first fixture revision used a rejected parent-traversal source spelling: all 64 attempts failed source admission before a model call. Its complete report and exact fixture bytes remain privately retained, separate from the measured revision-2 model cohorts. Runtime admission was not relaxed. The reviewed oracle correction permits retaining or withholding a shared grounded location in ambiguous reports without accepting invented paths; legacy path-scoring defaults are unchanged.

Final offline checks passed **350 tests, 81 deselected**, including installed-wheel resources outside checkout. Real Docker/Temporal/replay passed **11 tests, one live test deselected**. Pinned quality checks and wheel/sdist build passed; the existing uv build-version range warning remains. Both distributions have 147 entries without private/cache paths, and all wheel source/resource bytes match the final tree. Nothing was committed, pushed or promoted.

## Remaining qualification work

These repeated related synthetic cases cannot establish broad robustness, vulnerability accuracy or reliability on real scanner exports. Remaining errors are retained in private immutable artifacts and the per-format table. A correct intake decision does not establish a vulnerability or permission to execute arbitrary code. V3 producer/full-chain failures remain separate and were not rerun by this intake-only work.

Next useful gates are human-reviewed redacted real exports, held-out source/vulnerability families, explicit selection or batching for multi-finding reports, and deterministic matching of resolved requirements against reviewed inventory. Unknown/unrecognised layouts must retain a generic analysis path rather than require a scanner recipe. Any further runtime change needs its own identities, native checks and frozen repeats. No reliability threshold or safety clearance is claimed.
