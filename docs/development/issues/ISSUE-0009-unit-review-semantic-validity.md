---
id: ISSUE-0009
kind: issue
title: Unit review semantic validity
status: in_progress
updated: 2026-10-13
related: [SPEC-0078, PLAN-0093]
---

# Unit review semantic validity

## Observed and expected behavior

The live pre-execution assessment admitted an all-affirmative, artifact-bound review of benign input used as the exploit probe. Drafts also approved copied and wrong-module targets, but incidental citation-contract failures prevented their admission. Outcome blindness and immutable binding worked; semantic judgment did not. Both probes must call production logic, exercise their respective conditions and assert relevant properties with doubles confined to dependencies.

## Reproduction and evidence

Exact merged PR130 source df5c661242c0a833ab481803e116dc5add016e96, RIG0, configured self-hosted Qwen3.6-35B-A3B-NVFP4 provider. Command: `python -m evals.run assessment --set unit --provider-config /tmp/corsair-review-provider.json --results <ignored-evidence-root>/evals`. Native evidence: ignored `.runs/pr130-live-merged/evals/assessment/20261013T234854Z-unit-live/`. Seven attempts: two clean, four task/contract failures, one admitted semantic false approval. No baseline promoted. Operator provider settings: response8192, thinking2048, timeout180seconds; historical promoted settings differ.

## Attempts and diagnosis

The copied-target draft incorrectly equated identical test-local code with calling production. Citation validation rejected the draft for missing required plan references; this is not successful semantic detection. One broad rationale with four booleans did not force the reviewer to account separately for actual calls and values in both probes. Planning also failed native ID contracts; one valid SQL tautology failed a literal oracle marker. Preserve these distinct layers and all historical reports.

## Resolution criteria and next action

Implement explicit cited per-probe production binding, actual inputs/preconditions, assertions and substitutions, deriving revision validity from both probes. Keep outcome blindness, source/patch binding and exactly two native execution outcomes; optional witnesses remain optional. Run offline rejection/serialization checks and live positive/negative review cases, reporting semantic false approvals separately from contract failures. Resolve only with recorded evidence addressing the observed semantic failures; a schema change or scripted pass alone does not qualify model judgment. Broader languages/frameworks/CWEs and campaign execution remain independently qualified.
