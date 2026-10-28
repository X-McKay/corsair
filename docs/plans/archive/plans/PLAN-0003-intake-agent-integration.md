# Intake-agent integration on current main

Status: implemented and verified; merge authorized by the user's choice to integrate intake while preserving main, 2026-10-28. Base: main 12b1b14a; intake branch 76dd3129. The branches diverged before the redesign: the merge preview has 1,159 conflicts, so blanket conflict selection would discard unrelated work. Preserve current main as the integration baseline and port the bounded feature deliberately; do not replace its kernel, six verdicts, runtime drivers, scanner contracts, model route guards, frozen datasets or existing command semantics.

## Design and plan

Use the existing ADK runner and native Temporal coordination. Add the role-local intake agent/tools/skill, canonical bounded issue contracts in `contracts/intake_agent.py` (main's scanner envelope remains in `contracts/intake.py`), inspection-only Docker adapter, current-local-image inventory derived from main's configured runtime images, and ordinary intake activities/workflow. Keep reviewed packaged skills and source read bounds; no target execution, host fallback, pulls or new permissions.

Add an opt-in intake-gated investigation parent and typed API/CLI route. Existing admitted Case requests and scanner dry-run commands remain compatible. A raw issue can normalize and classify without a binding; executing main's trusted observer still requires an operator-owned Case binding. Missing binding stops categorically rather than inventing an observer or granting arbitrary test execution. A supported handoff must bind the issue location to that Case, committed intake, source digest, exact selected configured image and current configuration. Carry the immutable selection through preparation/manifest and Docker, with no tag/default fallback. Preserve main's coverage, semantic auditor, distinct-candidate negative threshold and evidence-scope policy unchanged. Intake usage and remaining time/calls span both stages; cancellation/deadline uses native child waiting and explicit uncertainty.

- [x] Establish current-main baseline with absolute PYTHONPATH and the existing root environment; preserve setup failures separately.
- [x] Port canonical intake, native agent/skill/tools/inspection and isolated frozen scanner evaluation; test JSON diversity and current inventory admission without altering old scanner APIs.
- [x] Add committed/pinned handoff into main's existing investigation activities and Docker manifest, with categorical stops before production and bounded aggregate recording.
- [x] Wire explicit CLI/API/worker routes and current docs, preserving all main commands and lazy-import behavior.
- [x] Verify native ADK, real Docker/Temporal/replay, cancellation, unsupported/missing binding/image/source/config changes, all-main offline/quality/package gates and outside-checkout resources. Fresh scoped review. Preserve failed/unrun model gates and known zero-tool-use/false classification limits.
- [x] Record results, create a merge commit that retains both histories with reviewed additive main integration, push and merge to main only after checks pass. Never force-update or overwrite remote main. No baseline promotion.

## Baseline setup observations

The first offline attempt used relative `PYTHONPATH=src`; subprocess checks changed cwd and loaded the old checkout, and terminal tests lacked TERM. It produced 13 failures / 1,052 passes and is a setup failure, not a main regression. The corrected baseline uses an absolute path and `TERM=xterm-256color`; 1,065 passed / 107 deselected in 25.32s on the unchanged main baseline.


## Implemented boundary

The additive port retains main's trusted payload-pair observer, recipes, six verdicts, source admission, provider guard, existing scanner intake and CLI/API commands. New opt-in `intake-agent` and `investigate --json/--issue` routes use the native ADK runner and Temporal children. Execution requires an operator Case binding; missing bindings stop as `TARGET_BINDING_REQUIRED`. A supported result is committed, revalidated against the request/config/source/target, and carries the selected immutable image into the producer and observer. Changed source or image stops execution. Native tests choose a different image from the configured default to detect accidental fallback.

A fresh review identified and corrected an unsupported tool/schema provider route, a scored-attempt summary bug, and elapsed-time sizing before sandbox setup/preloads. Regression tests cover the latter two, including an exhausted preload window with zero model dispatch. Source/runtime resource identity includes the native intake adapter. No new generated-code execution permission was carried over from the older branch: this is the explicitly selected main-preserving integration.

The intake dataset manifest discriminator changes to `corsair.intake-agent-dataset/1` to avoid colliding with main's existing scanner dataset schema. Input fixture bytes, hashes, labels and membership are unchanged. Manifest hash migrations (old → new):

- capabilities: `bb2137e8f159e0228bdf52f4052c64885c0951960dc3712c78ba2eb9139c2c55` → `35b2d2907d080cdd3d22e430170347d0e6fa3da0acfcd7889b4dc1db229f5755`;
- JSON candidate: `4c819a87a84caabadc877a0c5f28e2ae37ed74e1e5077350aeba5b7b8a270e39` → `410bdb1b92df5cf7a90f8eed2985bae9db79f931a7b3895933fde62db5d45273`.

## Verification environment and retained failures

Commands run in the main-based integration checkout with `UV_PROJECT_ENVIRONMENT=/Users/al/git/corsair/.venv`, absolute `PYTHONPATH` and `TERM=xterm-256color`, using the one root environment. The toolchain warns that the isolated checkout has no local `.venv`; a second environment was deliberately not created. UV also reports its existing build-backend version-range warning; no unrelated toolchain pin was changed.

The host is macOS arm64 with Colima Linux arm64. Colima cannot see macOS system-temp bind mounts: initial observer tests returned `invalid job` and two native observer failures. Building the current main Python observer did not resolve that setup issue. A strict harmless probe confirmed workspace temp mounts work and system-temp mounts do not. Native tests therefore set `TMPDIR="$PWD/.work/tmp"`, without weakening container admission, observation checks or cleanup. The prior image was retained as `corsair-python:pre-intake-main-20261028`; current reviewed image is `corsair-python:intake-main-20261028`, ID `sha256:98b49a605d71a094e9d6118ad41086f263d7f6b26268147283f5a4f5f02de1a2`. This was explicit qualification setup, not an intake recommendation pull/build.

Other retained development failures: duplicate pytest module names, a scanner dataset namespace collision, a CLI-test missing import, and the evaluator failure denominator omitting configuration refusal were corrected. An attempted nonexistent `just format` command failed; formatting then used the pinned Ruff directly. Earlier native aggregate had one test-only NameError / 31 passes; after correction the final set passed 32 / 1 live deselected before the last timing fixes. Final reruns are recorded below. These failures are not model or security evidence.

## Provider qualification limit

The requested endpoint is `https://llm.almckay.io/v1`, intake model `openai/Qwen3.6-35B-A3B-NVFP4`, LiteLLM connector. Current main rejects this tool/schema route for its tool-using producer; intake now preserves that restriction with `MODEL_CONFIGURATION_UNSUPPORTED`. The isolated eight-case diagnostic therefore reports 8 configuration refusals, 8 operational failures, 0 scored attempts and 0 model calls. No replacement provider was selected. Original raw reports, including the report before the failure-count fix, remain private under `.runs`. A repeated final frozen diagnostic after the last resource changes remains required below.

This integration is not qualified for live model accuracy or a full live provider chain. Prior branch diagnostics, including false-supported classifications and zero-tool-use outputs, remain historical limitations and are not promoted. Usage/cost unavailable from a model stays unknown. Other platforms/runtimes, hostile-source integrity and production readiness are not established by the executed scripted native chain.

## Final gates

Executed on the final product source:

- `nix develop --command just check`: passed pinned Ruff lint/format, Just format, ty with warnings as errors, and local documentation checks. Shared-environment warning above remains.
- `nix develop --command just -- test -q -W error`: **1,161 passed / 133 deselected**, 30.71s. Includes the built-wheel installation/resource test from outside the checkout and all existing main offline tests.
- `TMPDIR="$PWD/.work/tmp" CORSAIR_TEST_DOCKER=1 CORSAIR_TEST_TEMPORAL=1 PYTHONPATH="$PWD/src" /Users/al/git/corsair/.venv/bin/python -m pytest -q -W error -m 'not live' tests/integration/test_intake_pipeline_chain.py tests/integration/test_chain.py tests/integration/test_intake_chain.py tests/integration/test_intake_inspection.py tests/workflow/test_agent_intake_workflow.py tests/workflow/test_intake_pipeline_workflow.py tests/replay/test_history.py`: **32 passed / 1 live deselected**, 132.33s. Real Docker and Temporal; scripted native ADK models, actual observer evidence, immutable selected-image handoff, all categorical gates, cancellation/deadline suppression and replay.
- Final eight-case configured diagnostic: **8 configuration failures / 8 operational failures / 0 scored / 0 model calls**, report complete. Resource digest `71a52143dbe2abe23542b61446afe74ae25051dfc779ebb1ba316cfc9d435477`; configuration digest `25aafe5d5dca51b5ec0ad29b57a189d88aa64e1a4b56a3be983803f69409206b`. Final raw report `final-resource.json` retained privately. Cost/tokens unknown. The 32-case candidate cohort was validated offline, not rerun live during this integration; no full live provider chain or baseline promotion.
- `nix develop --command just build`: wheel and sdist built. Both contain 194 entries; inspected private/cache path exclusions, and wheel resources match every current package source byte. Outside-checkout installed resource/schema/API tests passed as part of the offline suite.
- Fresh read-only review confirmed the route guard and both final fixes; no remaining important defects found. No test claim is based solely on review.

Publication uses a main-based additive integration commit followed by an explicit history-preserving merge of the old intake branch, retaining the reviewed main tree. Remote main was refreshed and remained at `12b1b14a` before integration. The original `codex/intake-agent` branch and private evidence are retained. Merge/push receipt is recorded by Git; no force update, provider substitution or broad architecture replacement is authorized or performed.
