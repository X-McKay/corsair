---
id: SPEC-0077
kind: spec
title: Local Corsair results interface
status: accepted
updated: 2026-10-13
related: [SPEC-0044, IDEA-0009, PLAN-0091]
---

# Local Corsair results interface

## Goal and scope

The user requested a polished adaptation of the InfoSec Harness UI, integrated with Corsair, on a new branch/worktree. They explicitly selected inspection of existing results first. Provide a browser interface for saved agent evaluations, native investigation status and operator runtime records, with useful metrics and case details. No investigation submission, cancellation, evaluation execution, provider configuration editing, credential entry, policy editing in this slice.

## Boundaries and design

Adapt selected frontend patterns/helpers from the owner's infosec-harness UI at 52aa2ac, retaining provenance in ui/NOTICE.md. React/TypeScript/Vite consumes a same-origin read-only Python application. Local inspection uses the standard library loopback listener; deployment uses the same routes through pinned Gunicorn. No additional database, scheduler or web framework is introduced. Kubernetes uses operator-configured data mounts and an internal Service; remote multi-user access requires the operator authentication boundary described below.

The server projects bounded, allowlisted fields from .runs/evals/<agent>/<run>/summary.json and native report.json plus the operator runtime matrix. Raw inputs, model messages, source-bearing outputs, credentials, arbitrary file paths and hidden state are not API resources. Reject traversal and symlinks beneath evidence/assets roots, unexpected Host and cross-origin requests, unsupported methods and oversized evidence. Errors must remain visible without revealing private host paths. Serve only the built frontend directory with appropriate content types and security headers; never render evidence as HTML.

Overview, filtered evaluations, detail, agent metrics and runtime views expose observed counts, metrics/coverage, identities and limitations. Scripted/live model modes are separate from structural/executed evidence. All-checks-passed is not general security accuracy. Image-only runtime evidence is not live qualification. Unknown values stay unknown; measured zero stays zero. Incomplete/malformed reports do not appear as passing. Do not average unrelated datasets/providers into an accuracy claim. The user additionally requested overall/per-agent metrics, token and latency distributions, and the reference app visual aesthetic. Provide aggregate activity counts and recorded-identity cohorts with native per-attempt latency/input/output token histograms, observed token totals, success/completion rates, and individual correctness assertions. Keep missing identities separate and require explicit usage coverage for live token samples. Do not infer semantic accuracy from unrelated structural assertions or distributions from run means. Limits on files and sample counts must surface incomplete coverage. Use the user-requested Aladdin-inspired palette: black/white, neutral gray and teal, with strong headings and square-edged cards and controls. Adapt small-text accent shades for readable contrast. Include responsive navigation, keyboard-accessible controls, visible focus, loading/empty/error states, light/dark appearance and useful local CLI guidance.

## Acceptance and validation

Unit tests cover bounded projections, missing/partial/zero metrics, malformed evidence, confinement, request-origin/Host checks and static-serving restrictions. Build/typecheck frontend and test useful formatting/filter logic. Browser checks exercise production assets against the real API with synthetic saved-result fixtures and, where possible, a real scripted Corsair eval receipt. Exercise detail navigation, filters, theme, error/empty states and mobile overflow; inspect screenshots. These validate presentation/integration only, not live model accuracy or sandbox qualification. Run repository offline guards for integration changes.

## Decisions and open questions

Accepted scope follows the user's explicit read-only choice. Retain existing CLI execution and native evidence sources. No mocked dashboard presented as real results; synthetic browser-test fixtures stay clearly test-only. Existing report limitations remain visible. Broadening to launch work requires its own explicit execution boundary and future specification.

## Approved presentation design

The user approved the mock-up iteration: separate cards for each recorded agent, colocated outcomes and latency/token histograms with frequency-line overlays, an operational overview and a baseline/candidate experiment review. Each agent card selects one recorded identity cohort rather than combining incompatible results. Shared bin boundaries and frequency scales support resource comparisons; lines interpolate bin counts and do not estimate a probability density. Total-token samples require both input and output observations from the same native attempt. Accuracy stays undefined unless a future evaluator explicitly defines it.

The read-only experiment view selects two saved runs without promoting a baseline. Known incompatible agent/set/provider-mode/dataset identities block deltas; changed native execution modes also block when both are recorded. Prompt/model changes are disclosed as possible experiment variables. Case-level changes describe observed evaluator success rates, with missing cases/measurements unknown, and do not establish paired-repeat significance or causality. Mean efficiency coverage remains visible. No evaluation execution or new workflow boundary is introduced.

UI copy uses plain descriptive page titles, metric labels, instructions and error messages. Avoid slogans, rhetorical questions and promotional claims. Preserve measurement definitions, coverage and limitations needed to interpret results.


## Kubernetes data connections (accepted 2026-10-13)

The user expanded inspection to deployment alongside Corsair in Kubernetes. Use the same bounded projections and UI with a pinned Gunicorn WSGI adapter; the stdlib listener remains local-development only. This is not a new execution backend or scheduler. Serve assets separately from an explicitly mounted evaluation-results directory and the operator runtime matrix. Producer `CORSAIR_EVAL_RESULTS` and viewer `CORSAIR_UI_RESULTS` select the same storage. No example records ship in the image. A missing/unreadable directory is a source error, distinct from a readable empty directory. Readiness checks the required data/assets sources; liveness checks the web process, neither claims workloads are ready.

Add read-only native Temporal namespace and OpenShell health checks with explicit endpoint/TLS configuration and bounded calls. Unconfigured, unreachable and readable states remain separate. List at most100 parent Corsair chain/fixture workflows from the configured Temporal namespace, exposing identity/status/times only. Do not expose workflow payloads, histories, raw errors or results. Workflow status does not imply agent accuracy or available token telemetry. Evaluation metrics remain derived from saved native reports. The UI refreshes while visible and displays source errors; runtime registration is not a live service probe.

Render an internal ClusterIP Deployment/Service from required image, namespace, existing results claim and public origin. Read-only filesystem/mount, non-root user, no service-account token, no workload credentials and no public Ingress by default. Remote users require the operator's authenticated TLS ingress; preserve the configured Host and Origin checks. Temporal/OpenShell credentials are optional narrowly mounted service credentials, not model/source/workload credentials. Render/build/offline checks do not qualify a target cluster, its PVC contents or its service credentials. Production release needs an actual container smoke against real saved evaluation output and the deployment operator must verify the target mounts/connections.
