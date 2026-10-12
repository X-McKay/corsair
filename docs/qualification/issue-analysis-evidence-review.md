# Issue-analysis evidence review

This report covers the bounded auxiliary reviewer and direct sequence in [SPEC-0021](../development/specs/SPEC-0021-issue-analysis-evidence-review.md). It does not qualify the existing Temporal workflow, OpenShell composition, production reliability or a real benchmark case. Root owns shared inference/runtime and integration. Three independent Sol lanes implement/review the component, freeze evaluation inputs and adjudicate outputs.

## Isolated reviewer baseline: live001

Private evidence: `.runs/issue0007-resolution-20261012/reviewer-live001/`. The source freeze contains23 inputs; all hashes matched after completion. Eight independent candidates, each repeated twice, use the selected HTTPS `llm.almckay.io/v1` endpoint and `Qwen3.6-35B-A3B-NVFP4` alias. Immutable loaded weights remain unknown. Native prompted output, SDK/tool/task retry0, output correction1; per invocation requests6, source reads4, total tokens64000, response tokens16384, client120s and task300s; thinking remains server default. Inputs and oracle were separately frozen before implementation/evaluation.

Full offline283 checks passed in5.92s before dispatch. All16 live attempts completed typed, but only12/16 matched the frozen decision labels. Independent manual review found14/16 safe semantic decisions:

- Both irrelevant-citation candidates and both mutation-before-denial candidates were correctly rejected with source-grounded findings.
- All eight adequate candidates were supported, including justified missing-source abstention. Such abstention does not admit drafting.
- Fabricated ready analyses with no source were blocked for the correct absent-source/citation reason, but labeled `insufficient_evidence` instead of the oracle's `needs_revision`. These two finite failures remain unchanged; the first skill left this status boundary ambiguous.
- **Both existence-only return predictions were wrongly supported despite missing process read access.** This is a real unsafe semantic miss, not a rubric disagreement. A second agent alone did not resolve ISSUE-0007. The direct sequence stayed disconnected.

Native per-attempt messages, response IDs, output and exact quoted ranges, usage, elapsed time and the independent review are retained. Totals:33 model responses,12 source reads,57797 input tokens,39033 output tokens,34477 reported reasoning tokens and312.497s summed task latency. Both token dimensions were nonzero on all responses, with no failed or unanswered invocation in this run. Earlier unknown-delivery requests remain unknown in their original evidence.

## Next bounded candidate

Expose the reviewer's condition audit in a Pydantic output contract and require a sufficiency check of each material effect-producing operation. The procedure must hold the candidate's stated conditions true and check whether a normal unmentioned resource/format/access/branch condition can still change the claimed effect. This is general guidance; no case-specific permission predicate, hidden oracle or expected answer enters the agent. A supported ready review cannot contain an identified missing condition.

Four fresh independent native-operation contrasts were frozen under `reviewer-next/` before this change: conversion conditions and mutation order, with two adequate and two defective candidates. Keep their oracle separate. The first eight cases become regression cases, not fresh holdouts. Preserve live001 and its failures. Reviewer qualification and independent review still precede direct composition.
