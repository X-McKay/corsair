---
id: ISSUE-0011
kind: issue
title: Expanded producer candidate exact-payload diagnostic mismatches
status: open
updated: 2026-10-25
---

# Expanded producer diagnostics

The approved consolidation expanded the isolated producer diagnostic from one source case to three, while keeping the original fixture and oracle byte-identical. The two additions are AI-authored candidate fixtures pending human review, not a human-labelled held-out population. The expanded auditor diagnostic has four cases.

The original producer freeze passed3/3 and auditor6/6. The first expanded producer run passed4/9; its post-cleanup repeated run passed5/9. The expanded auditor passed12/12 both times. These are distinct actual live-model runs using the unchanged reviewed model settings and normal ADK factories. The full native regression suite's pass does not override diagnostic mismatches.

All four final producer failures returned valid string control/candidate values with matching controls, but candidates outside the declared exact-payload oracle list. There were0 operational/provider failures in the corrected final diagnostic. This demonstrates a limitation on the stated exact-match metric; it does not by itself establish that all four candidates are semantically invalid or non-exploitable. Native validity and semantic equivalence of those alternate strings have not been established. Do not edit oracle lists or label these failures as passes merely to improve the score.

Next bounded work: human-review the two candidate fixture designs and oracle alternatives, use trusted native evidence to distinguish equivalent candidate strings from invalid probes, and evaluate any source-grounding/prompt changes on unchanged and family-separated held-out cases. Prompts/permissions/runtime/oracles were not tuned in this consolidation. No candidate baseline was promoted and no population accuracy or negative-clearance claim follows.

Raw reports and typed outputs remain private under .runs/quality-consolidation-20261025. A [sanitized candidate receipt](../../../evals/baselines/candidates/expanded-diagnostics-2026-10-25.json) preserves both expanded attempts, original diagnostics, configuration identities and unknown cost. The distinct live safe-case operational failure remains [ISSUE-0010](ISSUE-0010-live-safe-case-probe.md).
