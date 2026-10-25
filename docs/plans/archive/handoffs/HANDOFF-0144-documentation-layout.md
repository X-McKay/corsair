---
id: HANDOFF-0144
kind: handoff
title: Project documentation hierarchy and packaged working-tree delivery
status: implemented
updated: 2026-10-25
related: [PLAN-0112, HANDOFF-0143, ISSUE-0010]
---

# Documentation hierarchy

## Scope and local state

Implemented the user's requested documentation hierarchy in `/Users/al/git/corsair` on `manus/just`. The existing uncommitted SDK/ports implementation and prior physical-Mac changes were preserved. The original-main stash `0ce65a61` remains untouched. No commit, push, merge, deployment or release was performed.

Start with [the documentation index](../../../index.md), [current work](../../README.md) and [PLAN-0112](../plans/PLAN-0112-documentation-layout.md). Root README, AGENTS, CONTRIBUTING, SECURITY, CHANGELOG and LICENSE now have separate roles. LICENSE records that no project-wide grant currently exists; no new license was selected. SECURITY does not invent a security address, private-reporting availability or production support SLA.

## Organization

Current pages cover getting-started; architecture and three implemented ADRs; development; task guides; operations and the actual pilot runbook; CLI/API/configuration/schema/glossary/platform references; and agent development/evaluation/safety. docs/index.md is navigation, and docs/plans/README.md is the single current-work index. Completed plans, handoffs, resolved issues and dated reviews moved into the archive; active safe-case ISSUE-0010 and the proposal backlog remain active.

The migration moved27 existing documents, repaired relative links and marked archival context. It did not discard unsuccessful attempts or rewrite old qualification into current results. The packaged risk assessment remains at src/corsair/policies/risk.md and is linked, not duplicated into a second runtime policy. All62 source/resource hashes matched the pre-migration checkpoint. No source, prompt, runtime configuration, policy, workflow, SDK/Nix pin or scoring change was made by this task.

## Validation and final workflow

The task followed implement, test, cleanup, retest and package:

- Before cleanup, locked `just check` passed and offline `just -- test -q -W error` passed103 tests with31 native/live tests deselected in35.41s.
- After final whitespace/navigation cleanup, `just check` passed again and the same offline suite passed103 tests with31 deselected in19.07s. Ruff lint/format, Just format and ty all passed; type warnings fail the gate.
- CLI `--help` succeeded for the root and all9 commands. Nine documented command forms parsed through the actual argparse parser. All19 Settings/ModelSettings fields were represented in reference,5 canonical Pydantic schemas generated, and documented Corsair imports resolved.
- All requested pages exist; local links, Markdown anchors, Python3.12 blocks and shell blocks were checked. Final counts and archive checksums live in the sanitized delivery receipt.
- Fresh source distribution and wheel built. The existing uv0.13.4 versus uv-build>=0.12.19,<0.13 build warning remains visible; no pin was changed to suppress it.

Documentation validation used cached project tools and UV_OFFLINE=1. The first cached Nix command was blocked at its existing daemon socket; the narrower offline command then passed with the required IPC access. A proposed native/provider-backed rerun was not executed because it exceeded documentation-only permission scope. No provider settings were accessed or copied, no services started and no targets/models invoked. Individual writing owners' blocked generic-cache checks were superseded by the parent's successful configured offline/CLI/schema checks, not counted as passes themselves.

The earlier134-test real Mac runtime suite and3/3 producer,6/6 auditor and2/3 composed-live results remain pre-documentation evidence. Current-local-revision Linux, Docker/Temporal and model evaluations were not rerun. The safe-case semantic failure is still [ISSUE-0010](../../active/ISSUE-0010-live-safe-case-probe.md), not a successful negative clearance.

## Delivery and follow-up

The delivery archive under outputs/docs-reorg-20261025 packages the actual working tree, not git HEAD alone, so prior uncommitted implementation is included. It excludes .git, .work, .manus, .state, .runs, .venv, caches, raw diagnostics and credentials. A manifest records included paths and SHA-256 hashes, base revision and dirty-tree status; archive integrity and local links are verified again from the archive.

Private task evidence stays under .work/docs-reorg-20261025. The user-facing report and sanitized verification receipt are under outputs/docs-reorg-20261025. No raw provider reports or private configuration are delivery dependencies. Future documentation changes should update the appropriate current page, not create another CURRENT.md or revive retired root docs paths. A future license decision belongs to the relevant rights holders.
