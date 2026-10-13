---
id: SPEC-0060
kind: spec
title: Runtime selection as the chain's first stage
status: draft
updated: 2026-10-13
related: [SPEC-0042, SPEC-0029, SPEC-0031, SPEC-0035, IDEA-0005, PLAN-0065]
---

# Runtime selection as the chain's first stage

## Goal and scope

SPEC-0042 built a deterministic detector, the operator runtime matrix and a hand-off (`nodes/runtime/environment.py`), but nothing in the E2E-0 chain calls them: every chain run uses the environment the operator declares in `FixtureCase`, whatever runtime the project needs. This spec makes runtime selection the chain's first stage in both modes (`run_chain` routing, used by direct mode and the durable workflow):

- a case may carry the build files of its baseline revision;
- the chain detects the requirement, selects a matrix row and resolves the row's prepared image on this node;
- `supported` continues, and the run records the selection; `unsupported`, `undetermined` and `not_prepared` end the run at stage `runtime` with the reason, before any model request, sandbox or revision run.

Excluded: running the environment agent inside the chain and mapping its `ReadyEnvironment` to the chain's `EnvironmentEvidence` (the rest of G12 in IDEA-0005), matrix rows (each image thread adds its own after its gate), changes to any agent package, its prompt or what a model is offered, and live runs.

## Boundaries and design

**Input.** `FixtureCase.runtime: RuntimeInputs | None`. `RuntimeInputs` (in `nodes/runtime/contracts.py`) carries the build files of the baseline revision's captured source (path to bytes, base64 on the wire so non-UTF-8 survives a Temporal payload), the agent-visible language when known, supplied Maven parent POMs and the project root. It is operator input like the rest of the case; agents never see it. Its build files and parent POMs total at most `MAX_INPUT_BYTES` (1 MiB): base64 makes that about 1.4 MB, so a whole chain request stays under Temporal's default 2 MB payload limit (measured: 1,401,456 bytes with the fixture case and 1 MiB of incompressible bytes). `runtime_inputs(files, ...)` builds the inputs from a snapshot's files: build files only, smallest first within the bound, and any file left out is named in `omitted`. Selection reports each omitted file as an unresolved input, so the outcome is `undetermined` in both modes instead of a server-side payload error in durable mode only (review of `993de00`). `None` keeps today's behaviour and is never silent: the run's limitations say the runtime was not selected from build files and the environment is the operator's declaration.

**Catalog.** `RuntimeCatalog(matrix, prepared)` is operator-owned worker configuration: the loaded matrix and the operator's image receipt (row id to `repository@sha256:...`). Its constructor refuses a prepared entry that is not a matrix row or not digest-pinned. Direct mode takes it as `run_direct(..., catalog=)`; the durable worker takes it in `configure_chain(..., catalog=)` (and `run_durable(..., catalog=)`), like the budget ceiling.

**Outcome.** `RuntimeOutcome` (pydantic, frozen) has `status` `supported | unsupported | undetermined | not_prepared`, the requirement (or the detector's reason when no single language applies), the selection, the prepared image when supported, a reason and, for every stop, the structured `Blocker` diagnostic (code, owner, actions, evidence lines) that #63 added to the hand-off. `nodes/runtime/environment.py` owns the decision (`runtime_outcome`), and `environment_input` now builds on it, so the chain and the environment agent's input share one set of stop reasons. `select_runtime(inputs, catalog)` is detect, select, decide; deterministic, no IO.

- `undetermined` covers both a detector reason (no recognised build file, several ecosystems) and an undetermined selection.
- `not_prepared` is a supported selection whose row has no prepared image on this node. It is the operator's gap, not the project's, so it is kept apart from `unsupported`.

**Routing** (`run_chain`, shared by both modes). A new `Stage` value `runtime` precedes identification. A `RuntimeSelector` port answers the selection: in direct mode it calls `select_runtime` in process; in durable mode it runs the activity `corsair.chain.select_runtime` (a frozen name) once, with no retry, on the worker that holds the catalog, so workflow code reads no file and replay sees the recorded outcome. A failure to select (no catalog configured, invalid inputs) stops at `runtime` with the native failure kind. A supported outcome is then checked against the operator's declared environment:

- `EnvironmentIdentity.image_digest` must equal the digest of the selected row's prepared image;
- `EnvironmentEvidence.language` must name the selected row's language (case-insensitive).

A mismatch stops at `runtime`: the run would otherwise execute on an image the selection did not choose. `DirectRun.runtime` and `ChainResult.runtime` carry the outcome in every case that reaches selection.

**Why bespoke.** Selection is a parser plus a set intersection already justified in SPEC-0042; this spec only routes its result. Temporal's activity is the native boundary for worker-owned configuration, the same as `execute_revision`.

## Acceptance and validation

Offline checks:

- Direct mode: supported continues to the gate with the outcome recorded; unsupported, undetermined (no build files; undeclared runtime) and not_prepared stop at `runtime` with no stage attempt and no revision run; an identity image or language that differs from the selection stops at `runtime`; no catalog stops with the failure kind; `runtime=None` records the limitation and otherwise behaves as before.
- Durable payloads: `ChainRequest` with non-UTF-8 build file bytes and `RuntimeOutcome` round-trip through the PydanticAI payload converter; the native Temporal tests (`tests/temporal/test_chain_native.py`, not in `make test-config`) gain a durable stop at `runtime` matching direct mode when the native test server is available.
- `environment_input` keeps its existing tests on top of the shared decision.
- Scripted evals: `make eval AGENT=chain` and `make eval AGENT=environment` unchanged (the frozen chain cases carry no build files, so they take the declared-environment path; the environment agent is untouched).

Live qualification is not part of this spec: a live chain over a real case also needs the environment stage, the case's matrix row and its prepared image.

## Decisions and open questions

- Selection reads the baseline revision's build files only. Both revisions run on the one selected image (the environment identity is shared); a fix that changes its runtime declaration is not detected here. Selecting both and requiring the same row is a candidate follow-up.
- The case's language is the operator's when given; otherwise the detector needs exactly one ecosystem at the root.
- Next: the environment stage (G12) consumes `environment_input` for a supported outcome and replaces the operator's `EnvironmentEvidence` with the mapped `ReadyEnvironment`; the identity check above then compares an observed image rather than a declared one.

The plan is [PLAN-0065](../plans/PLAN-0065-chain-runtime-selection.md).
