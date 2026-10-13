---
id: SPEC-0062
kind: spec
title: Live qualification tooling
status: accepted
updated: 2026-10-13
related: [PLAN-0067, SPEC-0045, SPEC-0046, SPEC-0042, SPEC-0007]
---

# Live qualification tooling

## Goal and scope

A RIG0 live run of a toolchain image took five to nine make invocations, four environment variables and several pastes, and harness wiring bugs (a missing evidence directory in the image-case harness, a per-test gateway that the first gate uninstalled) were found on the shared cluster. Al approved (2026-10-13 11:59Z, JDK 8 thread) a three-tier process and this tooling for it:

- `make qualify-image TOOLCHAIN=<dir> [CASE=<id>]`: the whole live chain on the checkout's own cluster, stopping at the first failure, reusing admission and network evidence while their own checks pass, with one `SUMMARY.md`.
- `make cluster-status` (read-only) and `make archive-runs` (copy a worktree's `.runs` into the main checkout).
- Offline stub smoke checks of every live harness inside `make test-config`.
- A checked-in RIG0 allow-rule file, a live-gate runbook in the base-image skill, and the process rules and four standing decisions in the development guide.

Out of scope: per-worktree cluster names (only if Al asks), a generic image-only case target (the Maven harness is case-specific), and any change to what a gate checks.

## Boundaries and design

The orchestrator (`tests/qualification/qualify_image.py`) only sequences the existing make targets, each logged under `.runs/qualify/<run>/logs/`. Reuse calls the same `require_admission` (gateway installer) and `require_network` (policy and toolchain gates) checks those consumers apply, on the newest five runs of this checkout or an explicit `ADMISSION_RUN`/`NETWORK_RUN`; a refused candidate is recorded with its reason. No trust logic is added and the provenance rule (evidence only from the installing checkout's `.runs`) is unchanged.

Order: tools, cluster (`kind-up` only without this checkout's receipt; `kind-up` itself refuses to adopt another's), admission (`admission-artifacts` and `admission-install` only when Agent Sandbox is absent), network, image build (skipped when the prepared receipt matches the sources; a mismatched retained cache stops the run), image load, gateway install, gate, then a fresh gateway and `qualify-<dir>-case`. Network runs before the gateway install so a network failure does not leave an unconsumed gateway. A retained `.state/openshell` stops the run (consume it with `make qualify-gateway`). The run refuses a dirty tracked tree, an existing run directory, an unknown image directory and a `CASE` with no case target. It never calls `workspace-storage`, `kind-down` or anything Al's pre-bash hook blocks, and never retries. Because `qualify-image`, `cluster-status` and `archive-runs` are pre-allowed on RIG0 with a trailing wildcard, the Makefile itself refuses them alongside any other goal or with any command-line variable outside `TOOLCHAIN CASE RUN ADMISSION_RUN NETWORK_RUN DEST`, accepts only an existing image directory as `TOOLCHAIN`, and passes the other values through the environment (validated again by the orchestrator), so no value reaches recipe text. An explicitly named admission or network run that its check refuses stops the run. Untracked files count as a dirty checkout.

Smoke checks run each Makefile marker as its own pytest session (as on RIG0) with a plugin that replaces the owned-cluster client, network fixture, native gateway, evidence checks and image receipts with stubs that stop at the first native call or gateway use. A test that raises anything else before that point fails `make test-config`, as does a marker whose tests install more than one gateway. They also resolve every live test's fixtures with the real conftest (`--setup-plan`), run `--help` for every harness CLI, drive the Maven image-case harness with stubbed Docker and runner, and drive the orchestrator with stubbed make and cluster answers.

## Acceptance and validation

- Offline: the smoke checks pass on the branch and fail on the two reintroduced bugs (function-scoped toolchain gateway; image-case `objects` directory not created).
- Orchestrator: fresh-cluster order, evidence reuse, first-failure stop, refused reuse recorded, retained gateway refused, all with stubs.
- Live: the first `make qualify-image` on RIG0 is its qualification; until then the target is implemented, not qualified.

## Decisions and open questions

The allow rules use mid-pattern `*` wildcards, which current Claude Code documents; Claude Code warns about a `*` before a subcommand, and the rules are a text match, not a boundary (the hook and deny rules stay; the deny list mirrors the hook's five substrings and refuses make options that replace or extend the Makefile). Whether RIG0's Claude Code version accepts them is unverified. Linked plan: [PLAN-0067](../plans/PLAN-0067-live-qualification-tooling.md).
