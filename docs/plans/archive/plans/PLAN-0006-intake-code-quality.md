# Intake operations and code quality

Status: completed locally 2026-10-29 on `codex/intake-code-quality`; base `f42832ed`. No commit or push was made for this quality pass.

## Scope

Implement the seven reviewed improvements: safe human intake/parent views; retained categorical diagnostics and correlated logs; readiness checks for intake models and images; discoverable stopped parents and explanations; single-purpose intake/CLI/Docker helpers; validated CLI argument combinations; complete image setup, current evaluator commands and environment-independent terminal tests.

Preserve ADK/Temporal ownership, canonical schemas, current payload-pair execution, pinned images, source admission, cleanup, immutable evidence and conservative verdict policy. No prompt, oracle, fixture, permission, runtime image content or execution capability changes are intended. Older stored results must still decode. Human output contains code-owned descriptions and allowlisted metadata only.

## Work and gates

- [x] Add failing behavior regressions and implement human views, parent navigation and CLI validation.
- [x] Preserve diagnostic categories and refactor intake preparation/output construction; add safe lifecycle correlation.
- [x] Extend read-only doctor checks to intake and reviewed images, retaining per-check failures.
- [x] Extract Docker workspace and receipt validation without changing lifecycle/cleanup; complete setup/docs/test fixes.
- [x] Run affected offline tests, quality checks, full offline suite, native Docker/Temporal and live intake chain, frozen intake diagnostic, package build and outside-checkout resources.
- [x] Fresh read-only review, resolve findings, update this record with actual results and remaining limitations.

## Baseline

Review reproduced model-authored text in human intake output, missing stopped parents from `runs`, and doctor model checks passing without inspecting an unsupported intake route. `just check` passed. The focused CLI suite was 177 passed / 2 failed under inherited `TERM=dumb`, then 179 passed with `TERM=xterm-256color`; terminal tests must own that environment themselves.

## Implementation

- Human intake and parent views render allowlisted metadata and code-owned explanations, including saved dictionaries. Image aliases sharing an ID display the actually selected reference. Complete JSON receipts retain issue/proposal content.
- `IntakeDiagnostics` is canonical and publicly re-exported. Stored results retain failure categories, validation/tool counts, stage and exception class, without provider bodies. Older receipts decode with defaults. Submission, progress, preparation failures and committed outcomes carry run identity.
- `doctor` reports individual configured-image failures, including the reader and extra candidates. Its optional model probes include intake text/native-tool checks and reject intake's blocked route before dispatch.
- `runs`, `inspect --explain` and `explain` admit and explain committed intake parents, including stops without children. Identity binding remains mandatory; native evidence still belongs to the child.
- Typed issue options validate inputs before file/service access. Standalone intake and connected investigation have separate handlers; finite waiting uses the existing native Temporal client helper. Source preload, packet construction, completion validation, workspace preparation and Docker receipt validation have named ownership boundaries.
- `just images` includes `image-intake`; evaluator commands and operator documentation match the installed package. Color tests set their required terminal environment.

## Verification and review

```text
nix develop --command just check
passed: toolchain, pinned Ruff lint/format, Just format, ty warnings-as-errors, local docs

nix develop --command just -- test -q -W error
1192 passed, 137 deselected in 32.27s

nix develop --command uv run --locked pytest -q -W error \
  tests/unit/test_intake_agent.py tests/unit/test_intake_cli_operations.py \
  tests/unit/test_terminal.py tests/integration/test_package.py
118 passed in 7.55s after the final protocol-signature/rendering edits;
includes installing the wheel and loading resources outside the checkout

TMPDIR="$PWD/.work/tmp" CORSAIR_TEST_DOCKER=1 CORSAIR_TEST_TEMPORAL=1 \
  nix develop --command uv run --locked pytest -q -W error -m 'not live' \
  tests/integration/test_docker.py tests/integration/test_intake_pipeline_chain.py \
  tests/integration/test_chain.py tests/integration/test_intake_chain.py \
  tests/integration/test_intake_inspection.py tests/workflow/test_agent_intake_workflow.py \
  tests/workflow/test_intake_pipeline_workflow.py tests/replay/test_history.py
41 passed, 1 skipped, 1 deselected in 148.35s

CORSAIR_LIVE_CONFIG="$PWD/.state/intake-e2e-20261029/settings.json" \
  TMPDIR="$PWD/.work/tmp" CORSAIR_TEST_DOCKER=1 CORSAIR_TEST_TEMPORAL=1 \
  nix develop --command uv run --locked --extra providers pytest -q -W error \
  tests/integration/test_intake_pipeline_live.py
4 passed in 83.94s

TMPDIR="$PWD/.work/tmp" nix develop --command uv run --locked --extra providers \
  python -m corsair.evaluation.intake_agent evals/datasets/intake-capabilities.json \
  --settings .state/intake-e2e-20261029/settings.json --repeats 1 --seconds 60 \
  --output .runs/intake-code-quality-20261029/frozen-8.json
8/8 complete and scored; 7/8 exact; 8/8 classification; 1 needs_input;
0 false-supported, invalid-output, configuration or operational failures

nix develop --command just build
wheel and source distribution built; each has 196 entries, with no private-state,
cache, database or bytecode entries in the inspected archives
```

The live supported run `temporal-live-intake-pipeline-42f5e54f00434653aadb` completed with `EXPLOIT_DEMONSTRATED`, using `corsair-python:0.1` and immutable image `sha256:98b49a605d71a094e9d6118ad41086f263d7f6b26268147283f5a4f5f02de1a2` throughout native receipts despite a deliberately unavailable default. The other three parent results stopped as `OUT_OF_SCOPE`, `UNSUPPORTED` and `TARGET_BINDING_REQUIRED`, with no investigation child. The CLI human view was also exercised against the real committed supported parent. Role models used the existing Qwen configuration at the user-authorized endpoint; private settings, reports, histories and evidence remain ignored.

The eight-case frozen diagnostic's `service` case classified correctly as unsupported but recovered only two of three expected requirement categories, so exact match remains 7/8. No fixture, oracle, dataset or runtime instruction changed. This is a role diagnostic with Docker inspection, separate from the four-case full chain. Cost remains unknown. The larger scanner cohort was not rerun; its contradictory-report defect remains [ISSUE-0001](../../active/ISSUE-0001-intake-conflicting-reports.md).

The live `diagnose_model` smoke used the same settings and only fixed synthetic probes. Configuration, credentials, all three text checks and intake's native-tool check passed. The producer tool check returned `warn` at the unchanged 128-token probe cap; this is inconclusive and is not reported as readiness. The full producer chain did run successfully with its normal budget.

Fresh read-only review found one P2: Docker list/read failures during mandatory preload could be mislabeled `MODEL_FAILED`. Both failures were reproduced before the fix; the adapter now preserves `INSPECTION_FAILED` and its exception class before dispatch, with zero model calls. Final unit/native-ADK tests cover both operations and private-error omission. Review found no other concrete regression in schema identity, saved-result compatibility, image handoff, cleanup or human-output privacy.

## Failed and unrun checks retained

Initial regression runs failed as intended for unsafe human fallback, missing parent navigation, discarded diagnostics, missing intake doctor checks and unhelpful issue-reference errors. One mistyped test filename produced no test execution. The first full offline run was 1189 passed / 1 failed because the architecture table omitted the new renderer; the table was corrected. Interim lint/type gates caught formatting, a missing non-null assertion and a reader-test parameter incompatible with its protocol; all were corrected. An inserted regression initially inherited two assertions from its preceding test and failed with `NameError`; those assertions were restored to their owner before the final passing runs.

Automatic approval initially blocked the live run over external-data sensitivity. Inspection established that the unchanged test transmits only the frozen synthetic case01 source/finding and fixed issue text, excluding private state and oracles; retry with that evidence and the user's explicit endpoint authorization was approved. No bypass or provider substitution occurred.

The opt-in 121-second Docker long-probe test was skipped; the related wait implementation did not change. Native checks cover this macOS arm64/Colima host and the stated Python fixture, not other host platforms, every runtime image, arbitrary hostile targets or general scanner accuracy. The wheel build retains the pre-existing uv/uv-build version-range warning. Concurrent Nix startup emitted an ignored cache-busy message during one successful targeted run. No qualification, baseline promotion, deployment or publication is claimed beyond these recorded gates.
