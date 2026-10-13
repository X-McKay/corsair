---
id: HANDOFF-0100
kind: handoff
title: OpenShell preparation for the chain's environment stage
status: recorded
updated: 2026-10-13
related: [SPEC-0070, PLAN-0077, SPEC-0068, PLAN-0075, HANDOFF-0096]
---

# OpenShell preparation for the chain's environment stage

## Verified state

Branch `claude/chain-runtime-handoff-dtb1ut` from main `ed9108b` (#106). Delivered under [SPEC-0070](../specs/SPEC-0070-openshell-preparation.md):

- `SandboxPolicy` port (`ports/sandbox.py`) and `CliPolicy` (`adapters/openshell_policy.py`): the pinned CLI's `policy set --wait`, counted only when the revision is observed loaded on the original sandbox.
- `OpenShellTestWorkspace.prepare_source`/`release_source`: the qualified SPEC-0032 placement with no test files.
- `UploadedVerifier` and `WorkspaceConfig(verifier=)`: a static Go verifier (`tools/workspace-verify`, `make workspace-verifier`) uploaded before the tree, admitted only when it reports the pinned SHA-256 of itself. Exactly one verifier route per workspace; the existing runner workspaces keep `python`.
- `OpenShellPreparation` (`adapters/openshell_preparation.py`): pre-flight policy and storage budget, placement, journal, dependency-setup policy, release and `sweep`; `PreparationRefused(layer, reason, cleanup)`; `read_source` answers from the operator's store.
- Live gate `make qualify-environment-preparation` (marker `environment_preparation`), which builds the verifier first.

## Validation and blockers

See [PLAN-0077](../plans/PLAN-0077-openshell-preparation.md#validation-and-progress). Offline only: the live gate has not run, so nothing here is qualified. The verifier needs Go 1.22+ on the gate host; whether RIG0 has it is unverified. Tree bounds are still SPEC-0032's 512 entries and 4 MiB, smaller than most corpus repositories.

## Decisions and next steps

- Upload route, not in-sandbox fetch: the images carry no `git`.
- The verifier is uploaded, never assumed in the image (Al: nothing in an image beyond language, framework and version).
- Next: the live gate on a fresh RIG0 cluster on Al's word; then raise the tree bounds from the operator's `WorkspaceBudget`; then the operator overlay (smoke test) once the port carries it, and a chain eval case with setup source.

## Continuation prompt

Continue from the SPEC-0070 PR: read SPEC-0070 and this handoff, verify the branch against main, then on Al's word run `make qualify-environment-preparation CORSAIR_NETWORK_RUN=<network evidence>` on a fresh RIG0 cluster and record the result in PLAN-0077 before asking to merge.
