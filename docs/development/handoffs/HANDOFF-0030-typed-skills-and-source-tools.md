---
id: HANDOFF-0030
kind: handoff
title: Typed agent skills and source tools with retained provider comparisons
status: recorded
updated: 2026-10-12
related: [PLAN-0018, SPEC-0019, SPEC-0020, ISSUE-0007, PLAN-0021, ISSUE-0006]
---

# Typed agent skills and source tools with retained provider comparisons

## Verified state

Started on clean main `32ef80e28ca3ae1d275247394ed28e1eead01381`, matching origin. The previous18 PRs were merged and baseline Development guards/indexing passed; HANDOFF-0029 predates the final merge. New Dependabot PRs19/20 are outside scope. Checkpoint `0c3514b021d11083fd90fb7fb2b6731bd8ea7446` was pushed; its Development guards38270763654 passed and remote main was rechecked. This handoff is committed with later work: resolve its published revision using `git log -1 -- docs/development/handoffs/HANDOFF-0030-typed-skills-and-source-tools.md`; do not infer it from the checkpoint.

The user redirected corpus work to ISSUE-0007, explicitly requested Sol research, active per-agent skills/tools/toolsets and PydanticAI structured output, and prioritized functional completion over token/latency optimization with warranted budget increases. Root owned integration/runtime mutations; three Sol agents independently researched/reviewed skills, native provider features, contracts and semantic contrasts.

Implemented: fixed operator-owned analyze-issue skill through native Capability, restricted native FunctionToolset, Pydantic input/draft/final contracts, native async structured output function and explicit numbered SourceRead/SourceLine tool results. Current-run read/scope validation precedes exact final quotation construction; public IssueAnalysis schema is unchanged. Native ModelRetry gives local coordinate feedback without translating or repairing invalid references. Native provider profile remains prompted structured parsing/validation, not strict provider JSON enforcement. No custom scheduler, provider protocol, generic repair framework, additional model tool or broad filesystem authority was introduced.

Explicit inference remains https://llm.almckay.io/v1, alias Qwen3.6-35B-A3B-NVFP4. Loaded weights identity remains unknown; observed historical cache metadata is not attestation. No deployment, credentials, policy, TLS or kernel requirement changed. No OpenShell runtime or real-project workload was created. All50 real candidates remain unqualified with zero real executions; PLAN-0021 and ISSUE-0006 remain independently gated.

## Validation and blockers

Current source checks: `make test-config`272 passed/5.82s (existing event-loop deprecation warning), native deterministic fixture6 cases/30 assertions, fresh scripted Temporal11/2.49s with six histories/replays. Final public JSON schema equality was checked against pre-change saved schema. Tests cover numbered/blank lines and native provider wire, current-run coverage, forbidden quotes, scope/unread/prior-run/disjoint-read failures and bounded native correction without an extra read. Independent implementation review found no substantive defect.

All owned ephemeral Temporal services were identity-checked and cleaned. Latest numbered-payload service PID2617865/start54051356 received SIGINT, exited0, original identity absent and ports17333/17334/17336 closed. Earlier stale native span assertion, record-template and exact inventory-label failures are retained alongside corrected checks. Old-history migration and real-provider durable/OpenShell composition remain unqualified.

[Provider assessment](../../qualification/issue-analysis-local-provider.md) and [PLAN-0018](../plans/PLAN-0018-local-issue-analysis-provider.md) retain every profile and actual result. Private evidence `.runs/issue-0007-research-20261012/` includes freezes/source copies, immutable reference/license provenance, reports/receipts, independent reviews and cleanup. Never commit it. Non-thinking and small thinking-cap candidates failed semantics; larger response budgets alone did not solve output/interpretation. Typed references removed model quotation copying. Live008 completed8/8 but retained a wrong path-parent precondition. First independent order holdouts completed2/4, failing on a citation correction followed by timeout and on response8192 exhaustion. Unanswered-request delivery/usage is unknown, not zero; no blind retry.

The subsequent coordinate skill/tool candidate live009 completed8/8,6 finite passes; two limitations flags are lexical, while manual review retained inaccurate join terminology and weak citation relevance. Fresh non-path heldout002 completed4/4 with core behaviors correct, but review retained conditioning/wording omissions. Both used explicit response16384/total64000/requests6/tools4/client120s/task300s/default thinking/no cap/output correction1/SDK-task-tool retries0. The private reference runner's default/report omissions are documented; actual invocation/config were frozen. Shipped CLI defaults remain2048/16000/4/2 and optional response4096/8192.

Numbered-read live010 completed8/8 typed,6/8 finite, with no native failures. Independent review confirms one genuine missing process read-permission precondition. The guarded finite flag is lexical: its cited line6 ValueError stops execution before line7 read_text, but the effect omits the evaluator's read keyword. It also includes an unnecessary caller exception-handling assumption. All six source-present outputs use narrow application/reference spans rather than the full73-line reference; one reference still describes resolve instead of directly supporting unguarded read_text. Provenance is valid, relevance/interpretation remain imperfect. Recorded totals21 responses/12 reads,55547 input/18135 output/14714 reasoning tokens,150.586534s summed attempt latency; provider usage exists on all8. ISSUE-0007 remains blocked. No rubric or failed output was changed and no further inference was dispatched. Its source-v12 manifest freezes55 inputs, SHA256 `e9f5dd5b8f8000ce0e14f15a5dda17c2c3a6cc7e948812a8b37d9cfdfc147869`. All55 current frozen inputs and their saved copies matched after the run; reference verifier passed. The source-present inputs uniformly include an exact immutable CPython reference excerpt; this private experiment admits neither production dependency retrieval nor an application interpreter version. Previous fresh cases are now regression evidence. A finite lexical pass or exact quote is not a semantic qualification.

Final process verification: development record checks4 passed/0.03s and `git diff --check` passed. Review and publication operate only on the enumerated tracked implementation/docs/tests; private evidence remains ignored.

## Decisions and next steps

ISSUE-0007 remains blocked by incomplete necessary preconditions and imperfect evidence relevance. Continue the bounded investigation using those actual remaining defects; do not keep tuning exposed tiny cases into a claimed heldout pass. Numbered source results are a general evidence-selection aid, not interpretation verification. New comparisons require separate freezes, appropriate independent cases and actual-output review. Preserve failed attempts and uncertain delivery. Keep semantics, provenance, completion, usage and native durability claims separate.

Existing authorization covers continued implementation/testing and periodic tracked commits/pushes, with root owning shared runtime mutations. No new approval gate is needed for that scope. Deployment changes or a different model are not implicit in a budget adjustment. Native OpenShell/PydanticAI/Temporal/Evals remain preferred. Real probes still require exactly two independently reviewed native tests, identical bytes on immutable vulnerable/fixed sources, actual discovery/control/security outcomes and effect witnesses, fresh storage/kernel/CNI/gateway plus concrete source/test/dependency recipe admission, and identity-checked cleanup. Existing fixed-source/runtime evidence cannot admit historical dependencies automatically.

## Continuation prompt

```text
Resume /home/al/git/corsair. Read AGENTS.md, README.md, docs/development/CURRENT.md and Corsair development/review/handoff skills, then HANDOFF-0030, PLAN-0018, SPEC-0019/0020 and ISSUE-0007; read PLAN-0021/ISSUE-0006 only as needed for dependent gates. Verify branch, local/remote state, current source and retained receipts before edits. The user prioritizes functional completion, native per-agent skills/toolsets and Pydantic contracts; budget increases are allowed when warranted, without weakening semantic/policy gates. Review the latest numbered-read live result and independent output review, then choose one bounded evidence-grounding/provider improvement with fresh independent contrasts rather than tuning exposed cases. Preserve unknown request delivery; do not blindly rerun it. Keep root as runtime owner and use Sol for independent research/review. No real corpus or real-provider durable/OpenShell claim follows automatically. Run affected checks, review final diff, update records/CURRENT.md and append a new handoff before stopping; commit/push within existing authorization, excluding .runs/.state/secrets/raw private logs.
```
