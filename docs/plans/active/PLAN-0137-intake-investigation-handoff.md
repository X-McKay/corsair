# Intake-gated end-to-end investigation

Status: implemented locally, 2026-10-28; final native/package verification recorded below. End-to-end live-model reliability remains unqualified. Authorized by the user to connect intake stopping and the selected producer test sandbox after PLAN-0136. Scanner evaluation and its open quality limits remain in PLAN-0135.

## Current gap and design

Standalone intake and v3 execution are currently separate. Execution accepts optional intake provenance, and the guide asks the operator to copy a supported result into a request. Add a concrete Temporal parent workflow for the normal investigation path: intake child, categorical gate, pure handoff construction with committed-provenance validation in the existing ordinary execution preparation activity, existing v3 execution child, immutable parent result. Workflows perform no I/O. Keep the existing low-level execution API available only as an explicit diagnostic route; the normal CLI/API must not silently bypass intake.

Only a completed `in_scope_supported` decision proceeds. Out-of-scope, unsupported, needs-input and error results stop before producer scheduling. Handoff requires the committed intake artifact and binds the original request, normalized issue, admitted source digest, configuration, exact selected inventory entry and immutable image ID. Reject a changed source/image or uncommitted/substituted intake. Never substitute a default image.

The selected image belongs in the existing producer packet and generic executor. ADK reasoning remains a worker activity; target/generated code runs only in Docker. Existing inspection uses its separate reviewed reader image. Executors already create containers from immutable image IDs and recheck availability before producer/auditor/execution; retain these checks.

Share finite budgets across both stages, including mandatory intake inspection reads. Preserve intake and execution results separately, aggregate usage without turning unknown tokens/cost into zero, and return explicit stop/incomplete categories. Cancellation uses native Temporal child/activity cancellation and waits for bounded cleanup; do not claim instant stopping or host-loss recovery. Add a separate workflow/versioned result rather than changing historical histories.

## Components and checks

- [x] Canonical issue-investigation request/result/handoff models under `contracts/`, public re-exports; one root budget in the nested intake request, no user-supplied execution image in the normal path.
- [x] Pure gate, remaining-budget and handoff validation under `policies/`; ordinary committed-artifact validation in existing execution preparation plus parent-result recording under `steps/`; concrete parent workflow under `workflows/`.
- [x] Wire worker, typed API, CLI investigate/inspect and documentation. Preserve standalone intake and explicit direct/legacy diagnostics, with no hidden automatic bypass.
- [x] Red/green tests for every stopped classification/status, budget exhaustion, image/source/config/issue substitutions, uncommitted provenance and missing image. Verify producer is never scheduled for stopped gates.
- [x] Real Temporal/replay and real Docker/ADK composition: choose a currently available non-default image, assert that exact immutable ID reaches producer and executor receipts, retain audit and cleanup boundaries.
- [x] Test cancellation and explicit failures; run required quality/offline/native/package gates and fresh scoped review. Run one new full-live-chain attempt separately from scripted native conformance, preserving provider/model failures.
- [x] Record actual outcomes and remaining gaps; update current guidance. No commit, push or promotion.

## Remaining limits

Workflow gating enforces the returned intake decision; it cannot make an incorrect model classification true. Existing scanner diagnostics contain false-supported examples. The current model may also ignore optional tools, and generated tests are not vulnerability oracles. Multi-finding selection/batching, human-reviewed real exports, held-out source families and live-chain reliability remain separate qualification work. Security assessment stays `UNRESOLVED`.

The concrete implementation reuses execution preparation as the existing I/O/validation boundary instead of adding a redundant handoff activity. The parent constructs the pinned execution request from its actual child result using pure checks, then execution preparation validates its committed artifact before scheduling producer. A new versioned aggregate returns child artifact references/outcomes rather than duplicating the bounded execution result payload. Standalone `intake` remains read-only analysis; normal `investigate` accepts issue input, while explicit `--direct`/`start_execution` remains the advanced diagnostic route.

## Implementation and review

Added canonical v4 `IssueInvestigationRequest`/`IssueInvestigationResult` with public re-exports, pure policies, ordinary aggregate-record activity and one native Temporal parent. Normal CLI supports raw `--json`/`--issue` plus `--source`, or a v4 request file. Typed `start_investigation`/`start_issue_investigation`, worker registration and offline/online inspection use the same path. V3 requires explicit `--direct`/`start_execution`; existing explicit legacy typed requests retain historical diagnostic compatibility. No user-provided execution image enters the normal request.

Execution preparation now requires committed intake provenance, recomputed supported decision, exact selected image metadata/ID, current configuration, normalized issue and admitted source snapshot before producer. Root accounting charges mandatory inspection reads; parent timers preserve the original deadline across child queue delay. Native cancellation waits for children and bounded cleanup, then parent retains categorical cancellation/deadline state even if the child catches cancellation and returns a recorded result.

Red/green checks included missing implementation, three previously accepted provenance failures (uncommitted intake, stale configuration, mismatched decision image), and API/CLI/loading behavior. The first combined offline run found duplicate pytest module basenames; the workflow file was renamed using ordinary imports. Early integration failures were missing required fixture fields/typed activity annotations, corrected without changing production admission. Review found the relative child deadline gap and cancellation-return classification gap; both were fixed with durable parent timers and post-await native cancellation/deadline checks. Native timer testing also caught the SDK's child-cancellation exception category; explicit deadline classification preserves it. These failed runs are not counted as passing gates.

## Qualification record

Final live and frozen outcomes are preserved in [the sanitized experiment](../../../evals/experiments/2026-10-28-intake-pipeline.md). The new full-live parent attempt stopped `UNSUPPORTED` with no producer scheduled; it is not a successful full-live execution qualification. The unchanged final eight-case intake diagnostic scored 5/8 exact, 8/8 correct decisions, zero false-supported/invalid/model failures and zero actual tool calls. Earlier scanner false-supported and original-cohort invalid/model failures remain evidence. Models, budgets, permissions and frozen inputs/oracles were not relaxed. Costs remain unknown.

Commands used for the live checks:

```bash
OPENAI_API_KEY=not-required CORSAIR_LIVE_CONFIG=.state/pipeline-20261028/settings.json \
  CORSAIR_TEST_DOCKER=1 CORSAIR_TEST_TEMPORAL=1 \
  .venv/bin/python -m pytest -q -W error tests/integration/test_pipeline_chain.py -k live
OPENAI_API_KEY=not-required .venv/bin/python -m corsair.evaluation.intake \
  evals/datasets/intake-capabilities.json \
  --settings .state/intake-json-20261028/settings.json --repeats 1 --seconds 60 \
  --output .runs/intake-json-20261028/pipeline-final-original.json
```

The non-secret dummy key is a deliberate environment input for this endpoint, not a product credential fallback. Live-chain test: 1 passed, 5 scripted cases deselected, 11.11s; passing means categorical result/artifact recording only. No provider or target execution was fabricated. Final package identity and command results follow below; no commit, push, PR or publication was performed.

Final executed gates after review fixes:

- `nix develop --command just check`: passed pinned Ruff lint/format, Just formatting, ty with warnings as errors, and documentation checks.
- `nix develop --command env TERM=xterm-256color just -- test -q -W error`: **389 passed, 102 deselected**, 11.18s. This includes installed-wheel imports and native packaged role/skill resources loaded outside the checkout.
- The real Docker/Temporal/replay command below: **31 passed, two live tests deselected**, 129.63s. The native comparison uses the already available Node/Java evolution tags; no missing default tag was pulled, built or silently replaced. The non-default image routing test explicitly keeps the Python default distinct.
- `nix develop --command just build`: wheel and sdist built successfully. Existing warning: installed uv 0.13.4 is outside the declared `uv-build>=0.12.19,<0.13` range. This warning was not concealed or fixed through an unrelated toolchain change.
- Wheel and sdist: **155 entries each**, no private/cache/credential/database state; every wheel source/resource byte matches the final working tree. `git diff --check` passed. Fresh scoped review confirmed the deadline and cancellation-return fixes and found no further defects. No cross-platform, hostile-source integrity, host-loss continuation or production-readiness claim follows.

```bash
CORSAIR_TEST_DOCKER=1 CORSAIR_TEST_TEMPORAL=1 \
  CORSAIR_TEST_NODE_IMAGE=corsair-node:evolution-20261025 \
  CORSAIR_TEST_JAVA_IMAGE=corsair-java:evolution-20261025 \
  .venv/bin/python -m pytest -q -W error -m 'not live' \
  tests/integration/test_pipeline_chain.py \
  tests/integration/test_execution_chain.py tests/integration/test_execution_sandbox.py \
  tests/integration/test_intake_chain.py tests/integration/test_intake_inspection.py \
  tests/workflow/test_pipeline_workflow.py tests/workflow/test_intake.py \
  tests/replay/test_legacy_history.py
```

The aggregate status is a coordination result, not a factual security outcome. Remaining failed/unrun qualification gates are successful full live execution, reliable producer generation, actual optional image-tool use by this provider, human-reviewed real scanner exports and held-out family/repeat evidence. Their absence is retained rather than inferred from scripted native success.
