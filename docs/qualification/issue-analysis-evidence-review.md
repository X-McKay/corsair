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

## Condition-audit comparison: live002

All 24 attempts completed with typed results; 22 matched the frozen decision label. Both original existence-only predictions were still incorrectly supported. The audit now mentioned readability but falsely called it stated in the analysis: one basis invented candidate coverage, the other used the API requirement as if it were a candidate assumption. Manual review also found incorrect audit attribution or branch relevance in attempts09/10,15,17/18 despite their correct final decisions. Therefore22/24 is not a count of fully sound audit reports and does not qualify the reviewer.

The four fresh conversion/order cases were run twice and classified correctly. They are now regression evidence. No baseline, oracle or receipt was rewritten. All31 frozen inputs matched at completion; retained copies and the frozen runner were independently checked. All responses have both nonzero token dimensions; no unanswered invocation occurred. Totals:45 requests,20 reads,89384 input tokens,66852 output tokens,57192 reasoning tokens and529.880s summed latency. Private receipts, native Evals report and independent review are under `reviewer-live002/` in the same evidence root.

## Anchored atomic candidate: live003

The next bounded candidate requires an atomic prerequisite and a typed locator into the immutable candidate's preconditions, conditional effect or capability statement. The trusted output function attaches the exact candidate statement. Source citations remain separate, current-run evidence. The skill distinguishes resource availability, acting-principal authority and value validity, and audits prerequisites for the predicted branch rather than success on an unrelated branch. Anchoring proves identity, not entailment or completeness; those remain independent semantic review obligations.

Offline `make test-config`:329 passed/6.04s before dispatch; independent code review found no new material mechanical defect. A separately frozen four-case set contrasts nonempty lists with valid offsets and integer divisors with nonzero divisors. Live003 ran16 cases (12 regression,4 fresh), two repeats each, with unchanged explicit model/profile/budgets. All37 frozen source/input hashes and retained copies matched at completion. Native Evals exited1.

29/32 attempts produced typed reviews; all29 decision labels matched the oracle, including all8 fresh-case attempts. Attempts08,09,12 exhausted native output correction after contradictory audit/locator fields. They remain failures, not completed semantic passes. Independent review found incorrect audit content despite correct decisions: mismatched branch conditions in18/23, combined premises under incomplete anchors in14/20, an unsupported path implication in13, claims that Python annotations enforce runtime types in26/27, and an unnecessarily nonnegative index restriction in29. The original omitted-read-access case was correctly rejected once; its repeat failed validation and also retained false entailment in its unaccepted draft. Thus29/32 is a decision-completion count, not29 fully sound reports. The reviewer and direct sequence remain unqualified.

All-attempt native reported totals:70 requests,28 reads,162351 input tokens,136599 output tokens,117456 reasoning tokens and1068.835s summed latency. These are partial reported totals, not a claim of complete coverage for failed runs. The29 completed attempts account for61 requests/25 reads/140292 input/114567 output/97920 reasoning tokens. The three failures retain9 requests/3 reads/22059 input/22032 output/19536 reasoning tokens, while their coverage flags and admitted aggregate token values remain unknown/null. No request was blindly replayed. Private receipts, native report and independent review remain under `reviewer-live003/`.

A subsequent native MockTransport test verifies full reviewer skill, audit/locator schema, candidate inventory and numbered source results reach the provider, and trusted anchors resolve correctly. Full offline330/6.10s passes. The restricted event-loop stall is retained separately from the permitted offline pass. A read-only native SDK inventory call confirmed the endpoint exposes only the selected alias; it does not identify immutable loaded weights.

## Remaining diagnosis

The invalid locator combinations are rejected by cross-field validators whose complete relationship is absent from the emitted schema. A small native Pydantic discriminated-union draft could express covered/missing alternatives and index/scalar anchors directly; it is proposed, not implemented or qualified. Preserve the final report and refusal rules. This may improve completion but cannot establish semantic entailment. The primary [Pydantic union documentation](https://pydantic.dev/docs/validation/latest/concepts/unions/) and an offline scratch schema support this design. Repeating native tool-output selection is not a new remedy: the earlier provider diagnostics already tried that lane. Larger budgets are not justified by these completed-response failures.

PR21 was independently re-reviewed and merged after this frozen run. It changes native provider selection and other boundaries; future comparisons must freeze and identify the integrated source, rather than treating live003 as qualification of that new source. No reviewer sequence, real-provider durable/OpenShell integration or model-authored test pair was executed.


Post-merge integration: full offline363/6.29s and the deterministic native fixture6 cases/30 assertions pass. The new reviewer wire test uses explicit `server="vllm"`; no additional real inference or durable/OpenShell qualification was run. See HANDOFF-0033 for the verified PR merge and continuation boundary.
