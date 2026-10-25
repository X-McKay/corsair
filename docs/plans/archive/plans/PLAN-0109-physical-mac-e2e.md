---
id: PLAN-0109
kind: plan
title: Physical Apple Silicon Mac end-to-end qualification
status: complete
updated: 2026-10-25
related: [PLAN-0108, HANDOFF-0142, ISSUE-0009]
---

> Historical record. Commands, counts and status describe the recorded revision, not the current working tree. See [current work](../../README.md) for current guidance.

# Physical Apple Silicon Mac end-to-end qualification

Completed the requested pull and bounded physical-Mac test investigation. Local `manus/just` tracks origin at `80e2ff56431ecc8e24d771c306ee203772ddbc69`. Final complete suite: **120 passed in 140.75 seconds**, no failures/skips, warnings as errors. This does not qualify the supplied Qwen producer: its separate frozen evaluation failed 3/3, so full live-model composition stays blocked by ISSUE-0009.

## Preservation and scope

Initial checkout was dirty main at `666d4962de4b3ba29139013b4dca1f7646be7fec`, with research documentation. Preserved tracked/untracked changes in named stash `0ce65a613e3da90534c40e3683d7851a3992df4b`, unapplied on the test branch. The original `.venv`, ignored state and prior evidence remain untouched; new SDK dependencies use `.work/mac-e2e-20261025/venv` and task-local caches.

Removed 148 untracked `.pyc`/`.pyo` files and 55 resulting empty directories under src; all 44 tracked source/resources were hash-verified unchanged. Final src has no bytecode-only directories or runtime Git diff. No branch reset, publication, merge, model fallback, schema relaxation or sandbox-policy weakening occurred.

## Completed checks and corrections

- Locked Nix Mac shell realized: Python 3.12.15, uv 0.13.4, Just 1.58.0, Temporal CLI 1.9.1 / Server 1.32.0. Ruff lint/format, Just format and warning-failing ty passed.
- Built pinned observer on existing Colima / Docker 29.5.2 arm64. First attempt failed writing Docker buildx activity metadata due tool permissions; a narrow buildx-cache grant resolved the diagnosed prerequisite without changing Docker policy. Image identity is retained in the sanitized qualification receipt.
- Actual Docker/Temporal/ADK chain and frozen batch passed. Full suite also passed native source/security, worker restart/cancellation/history replay, installed-wheel and real CLI process checks.
- Colima's default shared mounts do not include macOS's default native temp tree. Native `TMPDIR` and pytest `--basetemp` were pointed under the reviewed shared repository; both setup guides now document this.
- Native Mac testing exposed a real test-harness bug: PTY EOF can return empty bytes, but the original reader waited only for OSError. Fixed the bounded reader to stop on EOF, retaining every color/animation/native-evidence assertion. Two earlier stuck test PIDs were identity-verified through their task logs and stopped; incomplete attempts remain preserved, not relabeled passing.
- Direct original/fixed CLI references each succeeded with actual coverage and confirmed cleanup. Original: benign control PROPERTY_HELD / adversarial VIOLATION. Fixed: both PROPERTY_HELD. JSON output and safe start/completion log mirrors were verified without rerunning side effects. An inspection script's initial enum-name/value assertion was corrected; the actual CLI commands were not failures.
- Build and fresh installed-wheel test passed. uv emits a nonfatal backend-version-range warning; this is retained rather than described as warning-free tooling.

## Live endpoint results

The user explicitly supplied `https://llm.almckay.io`; TLS-verified catalog advertises Qwen3.6-35B-A3B-NVFP4. Initial auditor smoke exhausted its unchanged 512-token cap in default thinking mode. Existing native `reasoning_effort=none` then passed the same smoke and the unchanged two-case auditor freeze **6/6**, six calls / 4170 input / 719 output tokens. No larger budget or new provider wrapper was added.

Producer freeze: **0/3**, nine calls / nine tool calls / 11689 input / 1713 output tokens; nested PlanRevision arguments were strings and were correctly rejected. Native SDK reference schema is preserved; an inspected extra-type annotation was not emitted by ADK and was reverted before additional model calls. No full live-model chain was composed from this unqualified producer. Details: ISSUE-0009.

## Cleanup and evidence

Task-owned Temporal PID63892 was verified against the exact task database before SIGTERM. Loopback port17373 closed; no labeled security containers remained. Existing Colima, five pre-existing user containers and other Temporal services were left running. New observer image/package/cache/evidence remain available for reuse.

Private receipts: `.work/mac-e2e-20261025` and `.runs/mac-e2e-20261025`. Sanitized report/config/qualification: `outputs/mac-e2e-20261025`. Current changes are local test/docs/records only and were not committed or pushed. Continue with HANDOFF-0142; resolve and re-evaluate the producer before live composition.
