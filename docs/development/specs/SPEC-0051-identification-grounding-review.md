---
id: SPEC-0051
kind: spec
title: Identification grounding review
status: accepted
updated: 2026-10-13
related: [SPEC-0024, SPEC-0038, SPEC-0044, PLAN-0055]
---

# Identification grounding review

## Goal and scope

Comprehensive bounded review of inline and repository identification after PR47, preserving trusted original issue text and one source-grounded target. The user authorized per-agent reviews and improvements in independent worktrees and PRs. This change addresses invented partial symbol names accepted by the occurrence check; it does not prove semantic relevance, add a language parser or qualify downstream execution.

## Boundaries and design

Reuse the native PydanticAI finalizer and Pydantic contracts. Reject whitespace in symbol spelling and require a literal escaped occurrence bounded by identifier characters (Unicode word characters plus `$` for Java/JavaScript). Apply the shared finalizer to both modes. No policy, budget, tool, source authority, provider protocol or retry changes. Distinct grounding prompt/config identities reflect model-visible validation feedback; skill bytes stay unchanged.

## Acceptance and validation

Preserve the eight-case development corpus and compare baseline/candidate using `make eval AGENT=identification`. Add native negative cases for partial/whitespace symbols and prefix/suffix collisions, positive literal punctuation cases, repository-mode regressions and evaluator rejection of fabricated quotes at correct coordinates. The evaluator re-derives quotation from saved inline source separately from finalization; it shares the reader's line-splitting convention. Run focused tests and `make test-config`. Scripted results establish plumbing; bounded same-profile provider comparisons establish exposed-case observations only. Repository live smoke, held-out semantics, durable repository mode and real application execution remain unqualified or unrun here.

## Decisions and open questions

The bounded occurrence check can still match a comment or string, so semantic localization remains a model task evaluated by curated selections. No grammar or AST heuristic is introduced. Keep prompts/skills unchanged because the review identifies no measured defect needing their alteration. Broader independent repository cases and exposed-versus-held-out evaluation remain future work, rather than modifying frozen oracles to accommodate this candidate.

Review correction: identifier continuations now include Unicode combining/spacing marks through an adjacent-character identifier check, plus $. Literal occurrence remains a structural boundary check. Existing corpus and tool authority are unchanged.
