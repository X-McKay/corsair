---
id: HANDOFF-0033
kind: handoff
title: PR21 merge and reviewer evidence checkpoint
status: recorded
updated: 2026-10-12
related: [HANDOFF-0032, HANDOFF-0031, SPEC-0021, PLAN-0018, PLAN-0021, PLAN-0022, ISSUE-0007]
---

# PR21 merge and reviewer evidence checkpoint

## Verified state

The user explicitly authorized re-review and merge of updated PR21. Three Sol lanes reviewed immutable head `933f07188a7790dd99f7a80f51fe2a70228b9ab5`; root verified the previous partial-usage, merge-conflict and duplicate-handoff blockers were resolved. The combined tree with main `ed50ee1cf6062e9709bef9747c4f8d4e6d5be607` passed354 offline checks. PR21 is merged as `bc80d365630488810a2f18e9c7fa3208ba7bb0bb`; its actual tree `31d31aa8eca3f3d0266f5dceeda30edbe445bedf` exactly matches the tested tree. Development guards38281919396 passed on that merge commit. No additional critique was needed. HANDOFF-0031 and its linked comment describe the superseded old head, not current merge readiness.

Root preserved local ISSUE-0007 work as `33d9d49` before integrating the PR merge without conflicts. This handoff accompanies that integration; resolve its published revision with `git log -1 -- docs/development/handoffs/HANDOFF-0033-pr21-merge-and-reviewer-evidence.md`. The only source-test adjustment after integration adds PR21's required explicit `server="vllm"` to the new reviewer MockTransport test. The reviewer/sequence and native skills/toolsets were retained. No unrelated work or private evidence was staged.

Implemented: isolated native reviewer, Pydantic audit/locator contracts with trusted candidate-statement materialization, and a disconnected direct sequence with at most one fresh revision. ISSUE-0007 remains blocked. Real-provider reviewer composition, model-authored native test drafting, durable/OpenShell agent composition and all50 real benchmark cases remain unqualified. Corpus executions remain zero. PR21's provider, durable payload/name and OpenShell recipe changes require their own fresh qualification; historical fixture receipts do not qualify the integrated source.

## Validation and blockers

Pre-integration full offline330/6.10s passed; post-integration `make test-config` passed363/6.29s with the existing SDK event-loop deprecation warning. The new reviewer native wire test confirms skill/schema/inventory/tool delivery and exact trusted anchors; an earlier restricted-host event-loop stall remains distinct from its permitted offline pass. The integrated deterministic Pydantic Evals fixture passed6 cases/30 assertions, report `.runs/issue0007-resolution-20261012/integrated-fixture.json`. No live Temporal/OpenShell qualification was run for this merge.

Reviewer live003 is complete against the preserved pre-PR21 source. All37 frozen inputs/copies match. It produced29/32 typed decisions, all29 matching the frozen oracle; attempts08/09/12 exhausted native output correction. Independent review found incorrect branch/condition entailment in several completed audits, including fresh cases. Therefore correct decision labels are not a semantic qualification. The [review report](../../qualification/issue-analysis-evidence-review.md) records all three reviewer comparisons, exact failure layers, partial usage and independent review. Native receipts, private source freezes and reports remain ignored under `.runs/issue0007-resolution-20261012/`; no failed run or unknown usage was rewritten or blindly retried. The prepared direct composition runner was not dispatched.

The current endpoint exposes only the selected `Qwen3.6-35B-A3B-NVFP4` alias; immutable loaded weights are unknown. The native prompted profile is evidence-based: prior tool-output/JSON grammar lanes failed. Current failures did not exhaust the increased token budget. Cross-field audit/locator constraints are not fully represented in the emitted schema; a native discriminated-union draft is proposed, not implemented. It may improve output completion but does not solve the separately observed false entailment. All exposed cases are now regression evidence.

Independent primary-source JSPWiki research verifies vulnerable parent `f140a2a4371735ad24d04a1d78c6e1d9ceaed76f` and fix `88d89d6523802c044cfcb7930cba40d8eeb21da2`, licensing and historical native framework pins. Complete dependency closure, runtime compatibility and the concrete two-test recipe remain unadmitted. [PLAN-0021](../plans/PLAN-0021-multilingual-corpus-admission.md) and [benchmark progress](../../benchmark-admission-progress.md) retain the details. No OpenShell runtime was started; inference clients closed when the bounded evaluations ended.

## Decisions and next steps

Keep the original objective: resolve ISSUE-0007 before model-authored end-to-end probes. Do not connect the unqualified reviewer. A further comparison needs a concrete new diagnosis and a new frozen source/profile, not another replay of the same prompt or higher budgets without evidence. Native union-shaped draft contracts are a bounded completion experiment; actual entailment, branch relevance and adequate positive controls still need independent semantic evaluation. The integrated provider now requires explicit `server="vllm"`; preserved private runners target their historical frozen source and must not silently be treated as current commands. Do not change serving deployment or select a new provider/model implicitly.

Once the reviewer qualifies, evaluate the prepared one-revision direct composition independently, then exactly two native issue-validation tests with frozen identical bytes, actual discovery/control/assertion/effect witnesses and identity-checked cleanup. Every fresh live runtime still needs storage/kernel/CNI/gateway admission and a nonempty immutable source/test/dependency recipe. ISSUE-0006 continues to gate broader transfers. Existing authorization covers implementation, testing, tracked commits/pushes and the completed PR merge; policy, TLS, pins and kernel requirements remain unchanged.

## Continuation prompt

```text
Read AGENTS.md, README.md, CURRENT.md and the Corsair development/review/handoff skills. Read HANDOFF-0033, SPEC-0021, PLAN-0018, ISSUE-0007 and the reviewer qualification report. Verify git/remote/source state and retained live003 evidence; PR21 is merged, while its live provider/durable/OpenShell scope is unqualified. Preserve failed attempts and all current gates. Address the demonstrated native contract-completion gap only through a separately justified, frozen comparison; do not mistake a shape pass for semantic entailment or repeat previously failed provider modes. Keep root as sole live-runtime owner, use Sol independent evaluation/review, and do not connect the reviewer until its gate passes. Then continue the bounded direct composition and native two-test path under PLAN-0021/ISSUE-0006 admission. Run proportionate checks, update records and append a new handoff before stopping.
```
