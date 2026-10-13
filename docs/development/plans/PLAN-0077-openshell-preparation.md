---
id: PLAN-0077
kind: plan
title: OpenShell preparation for the chain's environment stage
status: in_progress
updated: 2026-10-13
related: [SPEC-0070, SPEC-0068, PLAN-0075]
---

# OpenShell preparation for the chain's environment stage

## Objective and dependencies

Implement [SPEC-0070](../specs/SPEC-0070-openshell-preparation.md) after #106. Depends on merged work: SPEC-0068 and PLAN-0075 (#100, #103), SPEC-0032 `OpenShellTestWorkspace`, SPEC-0026 `phase_policy`. Merging needs one live gate on a fresh RIG0 cluster, because this is a sandbox and policy change.

## Steps

- [x] `PolicyReceipt`/`SandboxPolicy` port and `CliPolicy`; scripted stand-in tests.
- [x] `OpenShellTestWorkspace.prepare_source`/`release_source` (the same placement and verification, no test files).
- [x] `OpenShellPreparation` with `PreparationRefused` and `sweep`; the stage records no cleanup for a refusal before any sandbox.
- [x] `PreparedSandbox.read_source` from the operator's store (the baseline file joins the planning inventory, #106).
- [x] Static uploaded verifier (`tools/workspace-verify`, `UploadedVerifier`, `make workspace-verifier`) so the route needs nothing in any image; the gate uses it.
- [x] Live gate `make qualify-environment-preparation`.
- [x] `make test-config`, evals, CURRENT.md row, PR, handoff ([HANDOFF-0100](../handoffs/HANDOFF-0100-openshell-preparation.md)).
- [ ] Live gate on a fresh RIG0 cluster before merge.

## Validation and progress

- 2026-10-13: Python toolchain image is the official slim image with no `git`, so in-sandbox fetch cannot run; card to Al recommends the qualified upload route, adapter written that way. The gate test collects; it has not run.
- 2026-10-13, Al: the route must be general, nothing image-specific beyond language, framework and version. The Python verifier needed an interpreter in the image, so it is replaced on this route by a static Go binary uploaded into each sandbox and pinned by SHA-256 (it reports its own digest). Built twice with Go 1.24.7: identical SHA-256 `36f009bf…08f1`. Its report equals the Python reference on 3 trees (nested directory, symlink, FIFO, truncation, cap).
- 2026-10-13, main `ed9108b`: `make test-config` 1807 passed (the Go conformance test ran here; CI skips it); `make eval AGENT=chain` 5/5, `make eval AGENT=environment` 16/16.

## Decisions and next action

Upload route first; the run records cleanup unconfirmed after a lost worker and the operator sweeps. Next: Al's word for the gate on a fresh RIG0 cluster.
