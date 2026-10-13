---
id: SPEC-0069
kind: spec
title: Local Corsair results interface
status: accepted
updated: 2026-10-13
related: [SPEC-0044, IDEA-0009, PLAN-0076]
---

# Local Corsair results interface

## Goal and scope

The user requested a polished adaptation of the InfoSec Harness UI, integrated with Corsair, on a new branch/worktree. They explicitly selected inspection of existing results first. Provide a local browser interface for saved agent evaluations and operator runtime readiness, with useful metrics and case details. No investigation submission, cancellation, evaluation execution, provider configuration editing, credential entry, policy editing or deployment in this slice.

## Boundaries and design

Adapt selected frontend patterns/helpers from the owner's infosec-harness UI at 52aa2ac, retaining provenance in ui/NOTICE.md. React/TypeScript/Vite UI consumes a same-origin, loopback-only read-only Python server. Python's existing standard library HTTP server is sufficient for a local evidence viewer; no production service, database, scheduler or new backend framework is required. It is not an authenticated multi-user deployment.

The server projects bounded, allowlisted fields from .runs/evals/<agent>/<run>/summary.json and native report.json plus the operator runtime matrix. Raw inputs, model messages, source-bearing outputs, credentials, arbitrary file paths and hidden state are not API resources. Reject traversal and symlinks, non-loopback Host and cross-origin requests, unsupported methods and oversized evidence. Errors must remain visible without revealing private host paths. Serve only the built frontend directory with appropriate content types and security headers; never render evidence as HTML.

Overview, filtered evaluations, detail, agent metrics and runtime views expose observed counts, metrics/coverage, identities and limitations. Scripted/live model modes are separate from structural/executed evidence. All-checks-passed is not general security accuracy. Image-only runtime evidence is not live qualification. Unknown values stay unknown; measured zero stays zero. Incomplete/malformed reports do not appear as passing. Do not average unrelated datasets/providers into an accuracy claim. The user additionally requested overall/per-agent metrics, token and latency distributions, and the reference app visual aesthetic. Provide aggregate activity counts and recorded-identity cohorts with native per-attempt latency/input/output token histograms, observed token totals, success/completion rates, and individual correctness assertions. Keep missing identities separate and require explicit usage coverage for live token samples. Do not infer semantic accuracy from unrelated structural assertions or distributions from run means. Limits on files and sample counts must surface incomplete coverage. Match the reference neutral/violet palette. Include responsive navigation, keyboard-accessible controls, visible focus, loading/empty/error states, light/dark appearance and useful local CLI guidance.

## Acceptance and validation

Unit tests cover bounded projections, missing/partial/zero metrics, malformed evidence, confinement, request-origin/Host checks and static-serving restrictions. Build/typecheck frontend and test useful formatting/filter logic. Browser checks exercise production assets against the real API with synthetic saved-result fixtures and, where possible, a real scripted Corsair eval receipt. Exercise detail navigation, filters, theme, error/empty states and mobile overflow; inspect screenshots. These validate presentation/integration only, not live model accuracy or sandbox qualification. Run repository offline guards for integration changes.

## Decisions and open questions

Accepted scope follows the user's explicit read-only choice. Retain existing CLI execution and native evidence sources. No mocked dashboard presented as real results; synthetic browser-test fixtures stay clearly test-only. Existing report limitations remain visible. Broadening to launch work requires its own explicit execution boundary and future specification.

## Approved presentation design

The user approved the mock-up iteration: separate cards for each recorded agent, colocated outcomes and latency/token histograms with frequency-line overlays, an operational overview and a baseline/candidate experiment review. Each agent card selects one recorded identity cohort rather than combining incompatible results. Shared bin boundaries and frequency scales support resource comparisons; lines interpolate bin counts and do not estimate a probability density. Total-token samples require both input and output observations from the same native attempt. Accuracy stays undefined unless a future evaluator explicitly defines it.

The read-only experiment view selects two saved runs without promoting a baseline. Known incompatible agent/set/provider-mode/dataset identities block deltas; changed native execution modes also block when both are recorded. Prompt/model changes are disclosed as possible experiment variables. Case-level changes describe observed evaluator success rates, with missing cases/measurements unknown, and do not establish paired-repeat significance or causality. Mean efficiency coverage remains visible. No evaluation execution or new workflow boundary is introduced.

UI copy uses plain descriptive page titles, metric labels, instructions and error messages. Avoid slogans, rhetorical questions and promotional claims. Preserve measurement definitions, coverage and limitations needed to interpret results.
