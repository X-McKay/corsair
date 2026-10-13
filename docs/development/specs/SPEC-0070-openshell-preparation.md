---
id: SPEC-0070
kind: spec
title: OpenShell preparation for the chain's environment stage
status: draft
updated: 2026-10-13
related: [SPEC-0068, SPEC-0032, SPEC-0025, SPEC-0026, SPEC-0029, SPEC-0006, PLAN-0077]
---

# OpenShell preparation for the chain's environment stage

## Goal and scope

SPEC-0068 runs the environment agent in a sandbox that an operator `Preparation` port prepares and releases; only a host double implements it. This spec adds the OpenShell adapter: one sandbox of the selected toolchain's prepared image holding the case's host-captured source, with the dependency-setup network policy (SPEC-0026) loaded before the agent's first command.

Excluded: in-sandbox source fetch (SPEC-0025) for now, because the toolchain images carry no `git` (the CPython 3.12 image is the official slim image); build-and-test narrowing inside the preparation sandbox (the revisions run on the operator's runners); private repositories (no registry egress for private source, SPEC-0026); the storage quota (SPEC-0036, deferred; the pre-flight `WorkspaceBudget` stands in); the dependency inventory node.

## Boundaries and design

**Source.** The host capture (`GitSource`, by exact commit) is authoritative, and the qualified SPEC-0032 `OpenShellTestWorkspace` places it: fresh sandbox, empty-root check, pinned CLI upload, in-sandbox verification of every path, mode, size and SHA-256 against the capture. `prepare_source`/`release_source` are that route with no test files. In-sandbox fetch stays the target once the images carry a pinned `git` (decision card, 2026-10-13).

**General across images (Al, 2026-10-13: nothing in an image beyond its language, framework and version).** The route assumes nothing in the image: the verifier is a static operator binary (`tools/workspace-verify`, Go, no cgo), uploaded into its own directory before the tree, never an interpreter the image happens to carry. It prints the same document as the Python `VERIFY` reference plus the SHA-256 of itself read through `/proc/self/exe`, and the host admits the inventory only when that equals the operator's pin of the file it uploaded. `WorkspaceConfig` takes exactly one route, `python` (the existing qualified runner workspaces) or `verifier` (`UploadedVerifier`); there is no fallback between them. `make workspace-verifier` builds it reproducibly for one Go version into `.state/tools/`.

**Inventory file.** `PreparedSandbox.read_source` answers from the operator's store over the same capture, never from the sandbox, so the chain can add the agent's chosen baseline test file to the planning inventory (SPEC-0068).

**Policy port.** `SandboxPolicy.apply(handle, policy, phase, operation) -> PolicyReceipt` (vendor-free, `ports/sandbox.py`). `CliPolicy` (`adapters/openshell_policy.py`) runs the pinned CLI's `policy set --wait` as the SPEC-0006 qualification does, then counts the revision only when `sandbox get` and `policy get --full`/`--rev` show it loaded and admitted on the original sandbox id. Stored but unloaded policy never counts. No retries; journaled intent and result.

**Adapter.** `OpenShellPreparation` (`adapters/openshell_preparation.py`), one per case, built by operator code from: a source-workspace factory for a digest-pinned image over the case's capture, the `SandboxExecution` whose workdir is the placed root, the policy port, the identity base policy, each ecosystem's resolver binaries and the `WorkspaceBudget`. Nothing comes from the agent.

**Prepare** (each step once, operation ids derived from the stage operation with `uuid5`):

1. Build the dependency policy and run the storage pre-flight. A refusal here (`policy`, `sandbox` or `host` layer) leaves nothing behind: `PreparationRefused(..., cleanup="not_required")`, which the stage records as no cleanup.
2. Place the source. A `WorkspaceError` keeps its layer and its own cleanup.
3. Journal the handle, then load the dependency-setup policy. A failure here discards the sandbox and reports whether that was confirmed.

**Release** deletes by the original handle and is `confirmed` only on an observed native delete.

**Leftovers (review of #103).** The durable activity is not heartbeated, so a start-to-close timeout does not cancel it and its `finally` still releases; a lost worker does not. `sweep()` deletes every journaled sandbox that has no confirmed release, by its original handle, under a fresh delete operation per pass. The operator runs it after a lost worker; the run has already recorded cleanup as unconfirmed.

## Acceptance and validation

Offline, with host doubles for the workspace and policy ports:
- the uploaded verifier goes in before the tree, and an executable other than the pinned one is refused and the sandbox discarded; a binary off its pin is refused before any sandbox; exactly one verifier route is configured;
- where Go is installed, the built verifier's report equals the Python reference's on a tree with a nested directory, a symlink, a FIFO, a truncated walk and a capped file (CI has no Go and skips it; the adapter tests use the reference as the binary's stand-in);
- step order and operation ids;
- each refusal keeps its layer and cleanup;
- refusals before any sandbox need no cleanup;
- release and sweep are confirmed only on observed deletes;
- a later sweep can confirm what an earlier one could not;
- `CliPolicy` against a scripted stand-in binary: a load observed on the original sandbox is recorded; a failed `set`, a revision not loaded, a replacement sandbox and an unpinned binary are refused.

Live, before merge (a sandbox and policy change): `make qualify-environment-preparation` on a fresh RIG0 cluster:
- the uploaded static verifier, not the image's interpreter, verifies the placed tree;
- the CPython 3.12 image and a captured revision holding the SPEC-0018 vulnerable module and its existing test;
- the scripted environment model's commands run in the real sandbox, and the stage is admitted ready from their receipts;
- both policy loads are observed;
- release is confirmed;
- a prepared-but-never-released sandbox is removed by `sweep`;
- no Sandbox resource remains.

The rest of the chain runs on the operator's sandbox runners and is recorded, not asserted.

## Decisions and open questions

- One adapter per case, so the `Preparation` port is unchanged; `PreparationRefused` carries the layer and what was left behind.
- Upload before fetch (decision card 2026-10-13); the in-sandbox fetch nodes stay for when images carry `git`.
- The tree bounds stay the SPEC-0032 ones (512 entries, 4 MiB); real corpus repositories exceed them, so raising them from the operator's `WorkspaceBudget` is the next limit to lift, separately qualified.
- Open: whether a later slice narrows to build-and-test inside the preparation sandbox once recipe phases are observed.
