---
id: HANDOFF-0148
kind: handoff
title: Final cleanup and authorized existing-PR publication
status: validated_for_push
updated: 2026-10-25
---

# Delivery record

User explicitly requested final cleanup followed by committing/pushing accumulated progress. The delivery target is the existing `manus/just` branch and PR197, whose base remains `manus/re-design`. No main/base merge, force push, second PR, new license, new provider or deployment is part of this delivery. Previous local documentation/source work and the original-main research stash remain preserved.

This handoff records the validated public tree and normal publication procedure. Exact pushed SHA, remote watch result and packaged checksums are recorded in final delivery receipts/Git metadata, not inferred from earlier CI or embedded circularly in the commit being described. Earlier handoffs remain historical records; their local-only statements are not rewritten.

## Final cleanup

Reviewed real component ownership, native factory/output-schema/tool usage, current import directions and resource-loading paths. The producer's private `_error` wrapper was used only at two read-only tool error returns; it was not SDK-registered. Removed that wrapper and two temporary variables, preserving the exact error dictionaries and native ADK tool signatures. Removed nine untracked bytecode-only directories under source; normalized excess blank lines in current instruction/navigation pages. No model instruction, permission, recipe, frozen source/oracle, runtime/toolchain pin or negative-clearance policy was changed during this last cleanup.

All accumulated changes include the native Pydantic output boundary, concrete ports/adapters and typed API/CLI, role-private resources, requested documentation layout, strict evaluation/test ownership, maintained Ruff/ty/documentation/import/privacy gates, verified local environment/state lifecycle and expanded unpromoted diagnostics. Tests contain intentionally labelled doubles; production agents use real native SDK paths, and mocks do not stand in for missing native/provider qualification.

## Actual post-cleanup validation

```bash
unset UV_PROJECT_ENVIRONMENT CORSAIR_TEMPORAL_ADDRESS
export UV_CACHE_DIR="$PWD/.cache/uv" PYTHONDONTWRITEBYTECODE=1 UV_OFFLINE=1
export OPENAI_API_KEY=EMPTY # Prior documented non-secret field for the reviewed unauthenticated endpoint only.
export TMPDIR="$PWD/.work/final-publish-20261025/shared-tmp"
export DOCKER_HOST="$(docker context inspect colima --format '{{.Endpoints.docker.Host}}')"
export CORSAIR_LIVE_CONFIG="$PWD/.state/qualification-20261025/settings.json"
nix develop --no-update-lock-file --command just sync check
nix develop --no-update-lock-file --command just -- test-all -q -W error
nix develop --no-update-lock-file --command just build
```

`just sync check` passed pinned Ruff lint/format, Just formatting, ty error-on-warning and maintained local Markdown checks. The full suite passed **150 tests, zero errors/failures/skips, in143.52s**. It used genuine SDK-owned Temporal dev servers, real Docker, actual CLI/replay behavior, native ADK conformance, a live-auditor smoke and a fresh wheel installed outside checkout. Frozen inputs and the old workflow/domain/policy/runtime pins were checked unchanged. Fresh wheel/sdist resources and privacy boundaries passed. uv's known cache/build-backend-range warnings remain recorded; no private/generated distribution members were found.

The final frozen expanded producer diagnostic scored **4/9**, with original case **3/3**; auditor **12/12**. There were zero provider/operational errors in these corrected runs. A sequential evaluator shell stopped at the failed producer score before auditor execution; the completed producer report was recovered and only the still-unrun auditor was invoked. No duplicate producer work or label repair was used. Candidate exact-string mismatches, prior5/9 repeat and earlier4/9 repeat remain distinct recorded outcomes. Cost stays unknown.

[Local publication receipt](../../../../evals/baselines/qualifications/qualification-publication-2026-10-25.json) preserves counts/identities and unrun gates. The separate full live-model batch was not rerun in this six-line final cleanup; its earlier **2/3** result and safe-case ERROR/INCONCLUSIVE remain [ISSUE-0010](../../active/ISSUE-0010-live-safe-case-probe.md). The expanded candidate metric limitation remains [ISSUE-0011](../../active/ISSUE-0011-expanded-producer-diagnostics.md). No human-labelled held-out promotion, production readiness, general hostile-source integrity or host-loss continuation is asserted.

## Publication and package review

Stage only public root policy/configuration and `src`, `tests`, `evals`, `docs`, `deploy`, `scripts`, `.github` paths. Review the staged rename/deletion map, whitespace, original frozen datasets/fixtures, packaged resource paths and credential signatures before commit. `.runs`, `.state`, `.work`, `.cache`, `.manus`, `.venv`, outputs, credentials, local databases, raw reasoning and private diagnostics are excluded. Signature scans are defense-in-depth, not proof against all possible secrets. Existing qualification receipts move byte-for-byte; new sanitized receipts are separate.

Commit with the required attribution and push normally to `origin manus/just`. Keep PR197 as the single progress PR. Watch CI for the exact new commit; a later remote gate may establish Linux/macOS native scope that earlier local receipts deliberately left unrun, but it cannot turn failed live diagnostics into passes. Remote runs without the user's provider cannot claim live-provider accuracy.

Package the exact committed source with `git archive`, fresh wheel and sanitized delivery/CI receipts; verify archive checksums, local Markdown links, category directory sets, runtime resources and absence of private/generated files. Final deliverables stay in ignored `outputs/final-publish-20261025/`. Retain local state/evidence/failed diagnostics and the preserved original-main stash. Do not prune uncertain operation claims or merge historical artifact stores.
