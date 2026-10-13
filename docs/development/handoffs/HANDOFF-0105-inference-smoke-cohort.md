---
id: HANDOFF-0105
kind: handoff
title: Runtime inference, operator smoke test and the corpus-python cohort
status: recorded
updated: 2026-10-13
related: [SPEC-0069, PLAN-0076, SPEC-0071, PLAN-0078, SPEC-0067, PLAN-0073]
---

# Runtime inference, operator smoke test and the corpus-python cohort

## Verified state

PR #115, branch `claude/eval-corpus-import-jcfaz1` from main `184e609` (after #97 and #106). Offline only; no case was run end to end.

- [SPEC-0069](../specs/SPEC-0069-inferred-runtime.md): `inference` rows in `deploy/runtime-matrix.yaml` (pytest, Jest, Test::More, Minitest, each citing its release metadata). A project with no declared runtime gets the newest qualified image in range, recorded as `runtime_basis: inferred` with `inferred_from`. Refusal paths: unread constraint or no covering row is undetermined; covering rows with no fitting image is unsupported, naming the runtime range or the declared tool that blocked it.
- [SPEC-0071](../specs/SPEC-0071-operator-smoke-test.md): `smoke` template data on each matrix framework row, carried on `RuntimeOutcome.smoke_tests`. It is written beside the capture by `Preparation.prepare(..., overlay=)` and offered as `EnvironmentInput.smoke_tests`. Finalization admits a smoke baseline only with its exact id, with a discovery command that does not name the smoke file, when discovery lists no other test, and when the operator's listing of the captured revision (`PreparedSandbox.source_paths`) holds no file the runner's default convention would discover (`checkout_tests`); an adapter without that listing gets no smoke baseline. `baseline_basis` is `project_test` or `operator_smoke`; the smoke file reaches planning through #106's baseline-file path, and the chain adds a limitation. Prompt `environment-v7-operator-smoke-test`.
- Corpus: `evals/corpus/issues.py` writes `corsair-issue-request/v1` issue JSON, a local bare repository and an evaluator-only `expected.json` per case. `corpus-python` (17 development cases) is committed under `evals/corpus/issues/`, with each repository given as its checkout-relative path. #109 will resolve that path against the checkout root (coordinator decision).
- Runtime report regenerated on `184e609` with the inference rows (corpus: 22 + 4 inferred, 3 declared supported, 7 unsupported, 6 undetermined).

## Validation and blockers

`make test-config` passes. `make eval AGENT=environment` scripted is 16/16. The Python, Perl and Ruby smoke templates pass natively on the host; the Jest and JUnit templates have not been run in their images (no Docker in the cloud container). The live environment eval against its baseline has not run (model server). `ih-python-healthcheck` and `ih-python-queryhelper` have no fixed revision, so the entry point refuses them until single-revision runs exist.

## Decisions and next steps

- The smoke file is written up front with the capture, because the sandbox is prepared once. Absence of a project test is checked from the run's own discovery output and from the operator's listing of the whole capture, not only by the skill. The OpenShell (#116) and Docker (#113) preparation adapters must supply `source_paths` before a smoke baseline can pass on them.
- Next: the first live case (`ih-python-pathtraversal`) through #109's entry point, then `SET=corpus-python`; the Jest and JUnit templates under the image-only harness; then the live environment eval.

## Continuation prompt

Continue from PR #115: read SPEC-0069, SPEC-0071 and this handoff, and verify the branch against main. Once #109 lands, run `ih-python-pathtraversal` from its committed issue file, record the result line, and route each stop by stage.
