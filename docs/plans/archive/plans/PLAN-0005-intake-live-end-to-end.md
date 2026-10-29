# Live intake-to-investigation handoff

Status: completed 2026-10-29; base main `80a64e42`.

## Goal and boundary

Verify the production CLI and worker composition with real Qwen intake, producer and auditor, Temporal coordination and Docker execution. Supported issues must carry the exact locally available intake selection to the producer manifest and every native execution receipt. Out-of-scope, unsupported and missing-binding inputs must stop before an investigation child. Main's operator-owned Case/recipe, canonical contracts, evidence, auditor and verdict policy remain intact. An issue by itself cannot invent a trusted target binding; this is an explicit prerequisite, not an automatic end-to-end claim.

The ADK producer itself runs in the worker. Target code and the trusted observer run inside the selected Docker image. No target code runs on the host.

## Implemented change

`EvidenceVerifier.evaluate` previously resolved the configured default image before the first role even when preparation carried an intake-selected image. That unrelated check could block a valid selected image. Pinned runs now omit only the default-image preflight. The Docker adapter still resolves the selected reference before every role, requires its immutable ID to equal the prepared manifest, creates the container by that ID and validates every native receipt against the same manifest. Unpinned runs retain the original default-image availability check.

The opt-in integration test invokes the normal `investigate` CLI, production activity composition and production worker. Its supported case uses the frozen public case01 operator binding, real Qwen models for all three roles, local image discovery, a deliberately nonexistent configured default, native Docker observations and a real Temporal server. It requires a fixed-source observation and checks the intake image ID in the manifest and every control/adversarial receipt. Separate out-of-scope, unsupported and missing-binding cases assert no investigation child is created.

## Results

The first live run completed four cases in 82.24 seconds. After review, the supported assertion was strengthened to require the fixed-source observation rather than checking it only when present. The final repeat completed four cases in 75.33 seconds. The supported run `temporal-live-intake-pipeline-6521ff07ed42425cb505` selected `corsair-python:0.1`, bound immutable image ID `sha256:98b49a605d71a094e9d6118ad41086f263d7f6b26268147283f5a4f5f02de1a2`, completed producer, native evidence, auditor and fixed-source execution, and returned `EXPLOIT_DEMONSTRATED`. Its deliberately unavailable default was `corsair-intake-unavailable:temporal-live-intake-pipeline-6521ff07ed42425cb505`. All role models were `hosted_vllm/Qwen3.6-35B-A3B-NVFP4`; the per-run configuration digest was `dd76919d9ff77c5a66e56c756ed77cb2ebb6a3f0cb6acd9b2f26922fea91a5f0`. The provider reported 20,942 input tokens, 4,448 output tokens and 41.90 summed role seconds; cost is unknown.

The final categorical cases stopped as `OUT_OF_SCOPE`, `UNSUPPORTED` and `TARGET_BINDING_REQUIRED`. Their parent histories contained only the intake child. No investigation child, producer, Docker target execution or auditor was started.

Commands and results:

```text
nix develop --command uv run --locked pytest -q -W error \
  tests/unit/test_evidence.py tests/integration/test_intake_pipeline_chain.py
28 passed in 0.54s

CORSAIR_LIVE_CONFIG=.state/intake-e2e-20261029/settings.json \
  TMPDIR=.work/tmp CORSAIR_TEST_DOCKER=1 CORSAIR_TEST_TEMPORAL=1 \
  nix develop --command uv run --locked --extra providers pytest -q -W error \
  tests/integration/test_intake_pipeline_live.py
4 passed in 75.33s

TMPDIR=.work/tmp CORSAIR_TEST_DOCKER=1 CORSAIR_TEST_TEMPORAL=1 \
  nix develop --command uv run --locked pytest -q -W error -m 'not live' \
  tests/integration/test_intake_pipeline_chain.py tests/integration/test_chain.py \
  tests/integration/test_intake_chain.py tests/integration/test_intake_inspection.py \
  tests/workflow/test_agent_intake_workflow.py \
  tests/workflow/test_intake_pipeline_workflow.py tests/replay/test_history.py
32 passed, 1 deselected in 135.14s

nix develop --command just -- test -q -W error
1167 passed, 137 deselected in 31.76s

nix develop --command uv run --locked --extra providers \
  python -m corsair.evaluation.intake_agent evals/datasets/intake-capabilities.json \
  --settings .state/intake-e2e-20261029/settings.json --repeats 1 --seconds 60
8/8 completed; 7/8 exact; 8/8 classification; 0 invalid, operational or false-supported

nix develop --command just check
passed: pinned Ruff lint/format, Just format, ty warnings-as-errors and docs checks

nix develop --command just build
wheel and source distribution built; the wheel contained 194 entries and no private state, cache or bytecode paths
```

The unit regression was observed red for the pinned case before the implementation change and green afterward. One composite approval request timed out before process creation; file status confirmed that it executed nothing, and the work was retried as bounded commands. The build retained the existing uv-build version-range warning. Private settings, histories, provider output and evidence remain ignored under `.state/` and `.runs/`.

## Qualification limit

This verifies the production handoff for one admitted standard-library Python fixture and three categorical gates on this macOS arm64/Colima host. It is not a population accuracy, hostile-source, cross-platform or arbitrary scanner qualification. The operator-owned Case binding remains required. The original eight-case intake diagnostic repeated at 7/8 exact and 8/8 classification, while the larger prior scanner cohort's contradictory-report false-supported defect remains open as [ISSUE-0001](../../active/ISSUE-0001-intake-conflicting-reports.md).
