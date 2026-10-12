---
id: SPEC-0020
kind: spec
title: Native typed citation references and exact evidence output
status: accepted
updated: 2026-10-12
related: [PLAN-0018, SPEC-0014, SPEC-0019, ISSUE-0007]
---

# Native typed citation references and exact evidence output

## Goal and scope

The issue-analysis agent currently regenerates verbatim quotations already returned by its source tool. Retained native runs fail exact quotation checks or exhaust output capacity, especially with admitted reference excerpts. Copying source bytes is unnecessary model work. Removing that obligation must preserve evidence attribution and the public final contract; it does not establish semantic correctness.

## Boundaries and design

Keep final `IssueAnalysis` and `SourceExcerpt` fields and constraints unchanged. The model-facing Pydantic `IssueAnalysisDraft` shares status/hypothesis/limitations rules but carries `SourceReference(path, start_line, end_line)` citations, with canonical path and ordered positive range validation and forbidden extra fields. The model cannot supply or replace quotation bytes.

Use an async native PydanticAI output function as `output_type`. Pinned SDK schema generation flattens its single Pydantic draft argument. The existing model profile selects prompted output for the local provider and native tool output for scripted fixtures. No custom JSON parser, repair pass, second model, scheduler or provider fallback is added.

The function verifies authorized scope and requires every reference to be enclosed by one successful `read_source` return in the current native run. It rejects unseen, out-of-range, prior-run and unsupported references with the existing bounded native output correction. Only then does the trusted in-memory source lookup supply exact quotations and construct the final `IssueAnalysis`. Source existence alone cannot authorize a citation. No host filesystem access or new model tool is introduced.

The native tool returns a Pydantic `SourceRead` with path/range and contiguous `SourceLine(number, text)` entries. Saved-file numbering is explicit; upstream numbers inside text remain content. The tool does not duplicate an unnumbered quote. The original immutable helper still returns SourceExcerpt; the output function validates current-run SourceRead coverage and uses that helper for final quotations. Preserve blank lines using exact newline splitting. This changes tool activity payloads and therefore requires fresh direct/durable validation.

The model owns interpretation and reference selection; the trusted output function owns quotation bytes. Native model messages retain the reference-only draft and tool results; final reports retain the enriched typed output. Evidence resolution must never be described as model-authored quotation or as verification of the hypothesis.

## Acceptance and validation

Check the actual native local-provider wire remains prompted with only `read_source`, flat Pydantic draft fields and no quotation field in citation references. Check exact final quotations, accepted read subranges, scope/unseen/unread/prior-run refusal, extra quotation-field rejection, status rules and existing request/tool/output-correction limits. Scripted evaluators project their old final oracle into draft references outside agent-visible inputs; final oracle equality remains unchanged.

Run affected offline/direct evaluations and a fresh native Temporal service, histories and replay. The async output function is deterministic and uses only saved inputs/current-run messages; native SDK durability remains responsible for execution. Historical output-tool identities do not establish cross-version replay compatibility.

Freeze each live comparison and preserve failures. Repeat original synthetic cases plus independently frozen renamed/order contrasts, including the uniform admitted library-reference profile. Correct quotations can accompany a wrong prediction, so independent semantic review remains mandatory. Keep ISSUE-0007 blocked unless the declared bounded profile completes its contrasts correctly; no application execution or real corpus admission follows automatically.

## Decisions and open questions

Two independent Sol reviews support this bounded contract change. The user has authorized implementation/testing; root owns integration and runtime mutations. This is a general source-evidence boundary, not fixture-specific logic or relaxed citation validation.

The current [native output-function documentation](https://pydantic.dev/docs/ai/core-concepts/output/#output-functions) and installed2.55 source support a typed argument, RunContext, native ModelRetry and a typed returned result. The installed version remains authoritative where documentation moves.
