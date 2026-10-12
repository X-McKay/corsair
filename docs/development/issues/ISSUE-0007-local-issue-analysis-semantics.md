---
id: ISSUE-0007
kind: issue
title: Local issue-analysis semantic and consistency gate
status: blocked
updated: 2026-10-12
related: [SPEC-0016, PLAN-0018, PLAN-0023, SPEC-0023]
---

# Local issue-analysis semantic and consistency gate

## Current assessment after PR22

Revisited on main `05f0946` after PR21 and PR22. The semantic gate remains blocked. PR22 implements evaluator data and individual-attempt label contracts, with separate exploratory/confirmation requirements; it neither changes the analyst skill nor provides a new live result. The current analyst SKILL.md exactly matches the last live010 freeze (`a9a9f0c5bd1dc63e3f62de5b7135af83128a27493d7492032d9fb2696e7c9d0c`). Agent, contracts, provider and source-tool modules differ from that pre-PR21 freeze, so neither old success nor failure counts qualify the integrated runtime.

The retained local evidence is available; the earlier PR22 implementation container's lack of it is not a current blocker. Reinspection verified 55/55 frozen source-v12 copies and 8/8 completed live010 receipts/input digests, with report inputs matching the frozen augmented fixtures. Three independently reviewed defects now have output and skill identities in `evals/issue_analysis/attempt_labels.yaml`: missing process read permission, an irrelevant reference citation and unnecessary caller exception handling. This is a small negative-example collection, not a balanced calibration or confirmation set. The legacy seed predates the skill file and remains excluded despite its recovered output identity.

Next bounded work is [PLAN-0023](../plans/PLAN-0023-issue-analysis-rubric-and-skill-protocol.md): complete independent per-output labels including clean examples and failed-attempt attribution; pair outputs with exact historical inputs/profile evidence; freeze disjoint exploratory and confirmation sets before judge use. The old live010 inputs include dependency references absent from the current public dataset. Joining by case name alone would score against different evidence. See the [evaluation data notes](../../../evals/issue_analysis/README.md) for identity encoding and coverage limits. No judge, candidate inference or direct analyst/reviewer composition ran during this reassessment. Larger budgets alone are not supported as the next remedy by the all-completed analyst run; consistent conditions and evidence relevance remain the demonstrated gap.

## Observed and expected behavior

The user-authorized Qwen3.6-35B-A3B-NVFP4 endpoint and native prompted SDK composition can return typed/source-grounded outputs, but fail the bounded semantic/consistency gate. A ready path hypothesis must state existence/read-permission and attacker-control assumptions and limit its observable effect accordingly. Missing source must yield missing facts. Hostile instruction and confined-source contrasts must complete within operator budgets without authority expansion or copied opposite claims. Typed validation alone is insufficient.

## Reproduction and evidence

[PLAN-0018](../plans/PLAN-0018-local-issue-analysis-provider.md), [assessment](../../qualification/issue-analysis-local-provider.md) and [runbook](../../runbooks/issue-analysis-local-provider.md) retain the exact command/config. Frozen live008 evaluates4 saved synthetic cases twice, concurrency1, promptv3/native prompted profile. Pre-run source-v1 freezes15 exact source/config/test/fixture/lock inputs and copies under ignored `.runs/four-priorities-20261012/pydantic-agent/`; all current/copy hashes matched after evaluation. Native report, eight receipts, logs and summary remain private there.

Only2/8 attempts pass all assertions (both missing-source). Five native failures: one exhausted output correction (ready result retained missing facts), four response2048 token-limit failures (both injection and both confined-source). Completed path repeat2 lacks file existence/read-permission preconditions and overstates returned content. It passed exact quotations/current-run read evidence; operation paraphrase and separate line3/line4 citations are legitimate and two rubric flags are false negatives, not additional model defects. Three completed tasks have17/18 assertions passed, which is not the success ratio of all eight attempts.

## Attempts and diagnosis

Native tool-output/JSON grammar candidates and indexing/system-message failures are separately preserved in live001–007. These lack full per-attempt source freezes and remain candidate diagnostics. Native supported profile changes solve typed/read request composition without custom repair, fallback, per-step scheduler or deployment changes; they do not solve reasoning/efficiency. Eight schema probes and selected SDK/vLLM source explain the strict-tool/response grammar interaction. The final matrix retains unchanged toolretry0/output correction1, requests4/tools2/tokens16000, response2048 and deadlines. No credential, policy, TLS or budget weakening occurred.

The frozen rubric also has finite paraphrase/citation false negatives. A guarded opposite-disclosure false positive was corrected before the final freeze with meaningful regressions. No report was edited or rubric relaxed to obtain a passing final result. Injection/guarded task failures provide no semantic verdict or resistance claim. Provider usage exists on all eight attempts; cost and loaded-weight identity remain unmeasured/unverified.

## Resolution criteria and next action

First review and improve the finite evaluator's paraphrase and combined citation admission using saved outputs/meaningful opposite claims; keep missing necessary preconditions and authority/guard defects failures. Freeze a new evaluator baseline rather than rewriting live008. Then undertake one separately planned native prompt/profile/model evaluation comparison with explicit selected model identity, fixed finite budgets and synthetic cases, retaining failed repeats and independent manual review. Require successful bounded source-grounded hypotheses with adequate preconditions plus completed missing/injection/guarded contrasts before semantic qualification. Do not expand private/live source acquisition, OpenShell, durable real-provider runs or full graph on this blocked result. Do not contact upstream or change the serving deployment without separate authorization.

## Promptv4 continuation

Rubricv3 corrected the two known false negatives with saved-output/opposite-claim checks; live008 still scores2/8 on offline rescore and remains unchanged. One frozen promptv4 comparison under identical provider/profile/budgets now completes5/8 with all finite assertions (both path, both missing-source, one hostile-source). One hostile-source attempt exhausts output correction; both guarded-source attempts exhaust2048 response tokens. CLI exits1. Actual-output review also records imprecise pathlib resolution wording missed by lexical predicates. This improves observed assumptions/completion but does not satisfy resolution criteria. No further tuning or retry was performed. See the appended [assessment](../../qualification/issue-analysis-local-provider.md) and HANDOFF-0026.

Next: preserve this candidate/baseline and independently qualify the manually reviewed native two-test vulnerable/fixed fixture pair before model-authored drafting. Real-provider composition remains blocked. Any further model/profile/contract comparison must be separately bounded and justified by these actual failures, not extra compatibility glue or repeatedly tuning the tiny suite to pass.

## Skills and structured-contract continuation

The user explicitly redirected the session to this issue, authorized Sol research and larger budgets when warranted, and prioritized end-to-end behavior over token/latency reduction. SPEC-0019 supplies an agent-owned procedural skill through native PydanticAI Capability, extracts the existing sole reader into FunctionToolset, and retains Pydantic input/output contracts and native prompted structured parsing/validation. Exact skill/schema delivery is wire-tested. No validation, TLS, policy or retry gate was weakened.

Private `.runs/issue-0007-research-20261012/` freezes each candidate and retains failed repeats. Non-thinking completed5/8 but passed only2 finite gates; a768-thinking-token probe produced a false guard prediction. Promptv5/response2048 passed5/8;4096 completed8/8 with6 finite passes but independent semantic defects. Skill-v1/4096 completed7/8 with6 finite passes;8192 also completed7/8 with6 finite passes. The latter failed malformed output then required limitations validation rather than the token cap; its hostile-source finite limitation flag is a false negative. Manual review still finds operation-order/API wording defects and, in the4096 skill run, an unrelated hostile-data example. No unauthorized host action occurred. The [assessment](../../qualification/issue-analysis-local-provider.md) separates finite results, manual findings, usage and failure layers.

Skill-v2 corrects the general schema-versus-instance instruction ambiguity. Offline263/5.73s, deterministic fixture6 cases/30 assertions and fresh scripted native Temporal11/2.43s pass; owned service cleanup is confirmed. These establish implementation/plumbing only. The subsequent uniform reference and native output-function experiments are recorded below; this earlier implementation checkpoint is superseded by their actual results.

The issue remains blocked. Preserve semantic and typed failures; do not promote a lexical pass, larger budget, skill directory, or reference file into real-provider qualification. Corpus executions remain zero; the separately executed synthetic two-test fixture does not close this agent gate. No deployment or new model selection is authorized implicitly by this investigation.


## Current typed-contract result and next action

SPEC-0020 is implemented and independently reviewed: model-facing Pydantic `IssueAnalysisDraft`, native async structured output function, current-run read/scope validation, deterministic exact quotation construction and unchanged public `IssueAnalysis`. Full offline270, deterministic6 cases/30 assertions and fresh native scripted Temporal11 pass. Agent skills and restricted tools live under the issue-analysis component and are delivered through native Capability/FunctionToolset. No custom parser or repair framework was introduced.

Uniform-reference live006 completed2/8; typed-reference live007 completed7/8; the final requests6/tools4/response8192/total32000 profile completed8/8 with7 finite passes. Independent review still found a wrong parent-directory precondition, so typed completion is not semantic qualification. The separately frozen operation-order holdouts completed2/4; one rejected citation led to a timed-out correction with unknown unanswered-request usage/delivery, and one response exhausted8192 tokens. Failed attempts remain in the denominator, without replay or a semantic verdict. Full results, usage and limitations are in the [assessment](../../qualification/issue-analysis-local-provider.md#typed-citation-references-and-independent-holdouts-2026-10-12).

Next bounded work should diagnose the retained timeout and response exhaustion at the provider/transport boundary before another live comparison. Use retained response IDs/timestamps and read-only serving evidence; do not blindly repeat uncertain requests or change the deployment. Any new inference profile must be separately frozen with adequate explicit budgets and new independent contrasts: these holdouts are now exposed and must not be tuned into a claimed held-out pass. Correct interpretation, necessary preconditions and current-source grounding remain required. The model alias does not establish immutable loaded weights. ISSUE-0007 remains blocked; no production source acquisition, real-provider durable/OpenShell integration or corpus admission follows from these results.


## Latest skill/toolset checkpoint

The user requested further development of agent skills/tools/prompts. The resulting general coordinate procedure and native correction feedback completed all8 original and all4 fresh non-path attempts under explicit16384/64000/6/4/120s/300s limits. Manual review still found inaccurate wording, omitted conditions and weak citation relevance. No new case-specific core logic or tool authority was added.

Current native read_source now returns Pydantic SourceRead/SourceLine entries with explicit saved-file numbering, while final IssueAnalysis remains unchanged. Full offline272, deterministic6/30 and fresh scripted Temporal11 pass, with identity-confirmed cleanup. Final live010 completed8/8 typed and6/8 finite. Independent review finds one real missing read-permission assumption, one lexical guarded false negative and one poorly matched reference span. Narrow citation selection improved, but correct structure/coordinates cannot establish correct interpretation. All55 frozen runtime/input/copy hashes match after execution.

ISSUE-0007 stays blocked. The immediate next bounded objective is consistent necessary preconditions and claim-to-evidence relevance using general procedural/contract guidance and independent evaluation. Further budget growth is not the remedy demonstrated by this final all-completed run. Preserve timeout/truncation history and investigate it read-only when relevant; do not blindly replay uncertain requests. No additional candidate, provider deployment or corpus execution is implied by this checkpoint. See HANDOFF-0030 and the assessment for final source/profile provenance and scope.


## Independent reviewer and observable condition audit

The renewed user objective is to resolve this gate before progressing to a full end-to-end run. [SPEC-0021](../specs/SPEC-0021-issue-analysis-evidence-review.md) evaluates a separate read-only reviewer with its own native toolset, skill, Pydantic structured output and receipts. Its initial live001 completed16/16 but wrongly approved the same missing-read-access defect twice. Two other exact-label failures correctly blocked fabricated source; keep those distinct. The [review qualification report](../../qualification/issue-analysis-evidence-review.md) preserves the baseline and independent adjudication. Adding another model invocation alone did not resolve this issue.

The next candidate exposes a bounded condition audit and forbids supported output with identified missing conditions. Strict Pydantic operator budgets and a disconnected one-revision direct sequence are implemented;321 offline checks pass. Independent fresh conversion/order contrasts were frozen before this change. Their live002 comparison is running with unchanged finite budgets; no pass, integration or issue resolution is claimed yet. The original analyst, fixed top-level graph and single-agent Temporal workflow remain unchanged.

Live002 subsequently completed24/24 but again approved the omitted-access case twice, with further inaccurate audit-attribution/branch items despite correct decisions elsewhere. No composition admission followed. The final bounded anchored-atomic candidate passes329 offline checks and independent mechanical review; its32-attempt live003 evaluation is in progress. Exact candidate references improve inspectability, but only independent evidence of actual condition entailment and branch relevance can qualify this reviewer.


Live003 completed at the preserved pre-PR21 source:29/32 typed, all29 decision labels correct, three native output-correction failures. Independent review nevertheless found wrong branch/condition entailment inside several audits, including fresh cases. All37 frozen inputs match. The reviewer remains unqualified and the prepared direct composition was not dispatched. Native skill/schema/tool delivery is now wire-tested; full offline330/6.10s passes. See the [review report](../../qualification/issue-analysis-evidence-review.md) for exact failures, partial usage and remaining native contract-shape diagnosis. That proposed schema change is not implemented and cannot by itself establish semantic correctness. Do not repeat previously failed output modes or infer that more tokens solve this result.

PR21's updated head933f071 was independently re-reviewed, its usage/merge/record-ID blockers verified fixed, and merged asbc80d365630488810a2f18e9c7fa3208ba7bb0bb. The actual merge tree matched the tested354-check combined source. Live provider, durable and OpenShell changes remain unqualified; future evaluation must freeze the integrated provider/contract source.
