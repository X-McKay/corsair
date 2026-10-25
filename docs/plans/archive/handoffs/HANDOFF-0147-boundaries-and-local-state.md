---
id: HANDOFF-0147
kind: handoff
title: Explicit composition, private local state and maintained quality gates
status: complete
updated: 2026-10-25
---

# Approved consolidation

Implemented in the local `/Users/al/git/corsair` working tree on `manus/just`. Earlier dirty implementation/documentation was preserved. No commit, push, merge, provider substitution or new deployment was requested/made. The original-main research stash remains preserved. Current source is later than the last pushed PR revision; old CI results do not qualify this local revision.

## Concrete changes

`Activities` now requires explicit store, inference, source-snapshot and sandbox dependencies. `entrypoints.worker.compose_worker_activities` constructs the actual ADK/local-source/Docker implementations around one store. No dependency container, alternate scheduler or registry was added. Shared lexical request normalization lives in `adapters.scm.requests`, avoiding evaluation-to-CLI imports; source symlink spelling stays intact. Role factories use native `str | BaseLlm`, not an adapter-only alias. Domain-only contracts/ports/policies, agent-factory directions and evaluation directions have maintained import tests, including relative imports.

`just docs-check` validates local Markdown destinations/anchors with a stdlib-only developer script; `just check` includes it. Ruff/ty cover that script. The checker skips private/generated/hidden trees and does not fetch external links; it is not a full Markdown renderer. Privacy regression tests check actual Git exclusions and ensure public sources/examples/datasets remain visible. The existing CI uses `just check`; no duplicate CI mechanism was needed.

All private/generated roots, deliverables, local databases/sidecars and common credential-file formats are Git-ignored; Docker's existing narrow build allowlist remains intact. The fresh wheel and source distribution contain no private/generated members. Generated delivery bundles are not source commits.

## Local lifecycle

The root `.venv` was recreated with pinned Nix Python3.12.15 and locked uv dependencies. It passed40 focused tests,119 offline tests and two150-test complete native/live/package runs before dated task/rollback environments were retired. Those virtualenvs were never executed at their relocated backup paths. uv cleaned the old task cache; ongoing cache use is standard uv caching, optionally `.cache/uv`. There is no custom cache engine.

Two exact closed task-owned Temporal databases moved from scratch to `.state/temporal/history` using SQLite backup, `integrity_check`, logical dump digest equality and byte-identical original snapshots under `.state/backups`. Quiescence and absence of sidecars were checked first; originals were removed only after verification. Three reviewed settings files moved unchanged into private settings history. `.state/settings.json` provides ongoing defaults; an isolated qualification configuration and new database were used for this run. Existing `.runs` stores were not merged/moved and old histories were not restarted as new services. Legacy Ollama/provider bridge/TLS/private-key state remains untouched.

Twelve verified passed-test temporary trees, two duplicate environments and the old task cache were retired after their receipts/validation. Remaining `.work` material has explicit retention notes: failed-test scratch, source/checksum checkpoints, scripts and logs remain available. `.work` allocation was1,902,760KiB at initial inventory and259,456KiB after final cleanup (roughly1.57GiB less in that directory); this is a local `du` comparison, not a claim about physical disk snapshots or total host free space. New environment/cache/state allocations are separate. Complete run stores, unknown-operation claims, raw failure evidence, settings history and database rollback snapshots remain retained.

## Exact final gates

From the repository root, use `nix develop`, the canonical environment and the reviewed Docker daemon. Qualification used a repository-shared `TMPDIR`, a unique task-owned loopback Temporal service at17376, and `.state/qualification-20261025/settings.json`. The existing user-selected unauthenticated model endpoint advertises the configured model; the earlier handoff's `OPENAI_API_KEY=EMPTY` is a non-secret required client field, supplied to test/worker processes only. Runtime does not fabricate keys or bypass TLS.

```bash
export UV_CACHE_DIR="$PWD/.cache/uv"
export PYTHONDONTWRITEBYTECODE=1 UV_OFFLINE=1
export OPENAI_API_KEY=EMPTY # Only for the explicitly reviewed unauthenticated endpoint.
export DOCKER_HOST="$(docker context inspect colima --format '{{.Endpoints.docker.Host}}')"
export TMPDIR="$PWD/.work/quality-consolidation-20261025/shared-tmp"
export CORSAIR_TEMPORAL_ADDRESS=127.0.0.1:17376
export CORSAIR_LIVE_CONFIG="$PWD/.state/qualification-20261025/settings.json"
nix develop --no-update-lock-file --command just check
nix develop --no-update-lock-file --command just -- test-all -q -W error
nix develop --no-update-lock-file --command just build
```

The service prerequisites are now **stopped**; the commands above record exact successful qualification conditions, not a self-starting current recipe. Use [local files/setup](../../../development/local-files.md) to deliberately start an intended service. Test fixtures can also manage their native dev server when no external address is provided.

Initial full suite:150 passed,0 errors/failures/skips,170.87s. Final post-code/storage-cleanup suite:150 passed,0 errors/failures/skips,152.43s. Offline:119 passed,31 deselected. Pinned Ruff lint/format, Just format, ty error-on-warning and maintained documentation checks pass. The full suite includes real Docker/Temporal, CLI progress/detachment, replay, genuine native ADK conformance, live-auditor smoke and a fresh installed wheel/resources outside checkout. Scripted composition is explicitly not full live-model accuracy.

The initial new-cache offline wheel-install attempt failed because dependency downloads were unavailable; the same package gate passed after locked fetch, then the whole suite passed with the warmed cache. Initial isolated-model attempts failed before inference because the documented EMPTY SDK field had been omitted; all attempted rows with unknown telemetry remain recorded. These failures were not removed or relabelled.

## Evaluations and unresolved limits

Original frozen development diagnostics:producer3/3, auditor6/6. Expanded candidate cohorts retain original inputs and add two source-grounded producer cases and two outcome-blind auditor cases. They are AI-authored candidate diagnostics pending human review, not a held-out/promoted population baseline.

First expanded producer4/9; final post-code-cleanup repeat5/9, with0 provider/operational errors. All four final failed rows had matching string controls and string candidates outside the exact oracle list. Their native validity/semantic equivalence is not established; do not label every mismatch a proven invalid exploit or add alternatives merely for green scores. Original producer case remained3/3. Auditor12/12 on both expanded attempts. [ISSUE-0011](../../active/ISSUE-0011-expanded-producer-diagnostics.md) owns follow-up.

The separate actual live worker/model/Docker/Temporal batch completed and scored2/3. Vulnerable/fixed and component-scope paths passed; safe case remainedERROR/INCONCLUSIVE. [ISSUE-0010](../../active/ISSUE-0010-live-safe-case-probe.md) remains open. When the client's terminal handle was lost, the already saved report and Temporal completion identity were recovered; the batch was not resubmitted. Missing cost stays unknown. Qualification receipts are separate from candidate/promotion baselines; five previous qualification files moved byte-for-byte with Markdown backlink repairs only.

Deterministic request/dataset loading was measured with five repeated local microbenchmarks before/after; no overall agent speedup follows from those figures or from the two suite durations. Native Temporal logged one slow workflow task during concurrent first-import work; the safe warning is retained, not silently suppressed. uv warned about a project-local cache and a build-backend range not matching its current builtin version; inspected fresh distributions contained0 private members. Runtime/dependency/toolchain pins, prior fixtures/oracles, workflows, domain contracts/policies and settings definitions remain unchanged.

Current-revision Linux native/CI qualification, human-labelled held-out promotion, hostile-interpreter integrity, host-loss recovery and production readiness remain unqualified. See the [qualification receipt](../../../../evals/baselines/qualifications/qualification-consolidation-2026-10-25.json) and [candidate receipt](../../../../evals/baselines/candidates/expanded-diagnostics-2026-10-25.json).

## Cleanup and next action

Only exact task-owned worker/server identities were signalled withSIGTERM; both exited0, the worker recorded graceful stop, and retained qualification SQLite passed integrity check. No Corsair security-labelled containers remain. Unrelated services were untouched.

Start next work with [plans](../../README.md), human review of candidate fixtures and bounded native validation of alternate probes. Preserve complete artifact stores/intents and state provenance; no blanket cleanup, automatic baseline promotion or generic negative-security result is warranted.
