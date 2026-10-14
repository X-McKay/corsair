# Corsair v2 validation checkpoint

**Checkpoint date:** 2026-10-14. **Branch:** `manus-test`.

This is an implementation-progress checkpoint, **not a production-runtime qualification or an agent-quality release approval**. The branch contains a CLI/library implementation; it contains no website or web console. Production execution has no mock-inference or host-shell fallback. Deterministic model and sandbox doubles are confined to tests.

## Verified offline checks

| Check | Last completed result |
| --- | --- |
| `uvx ruff check src/corsair/v2` | Passed, including the repository's configured rules. Deliberate foreign-library failure boundaries and stable `ValueError` admission contracts carry inline explanations. |
| `env -u PYTHONPATH uv run pytest tests/v2 -q` | **103 passed** in 8.95 seconds. One non-failing pytest collection warning concerns the imported `TestRecipe` contract name. |
| Python compilation | Passed for the v2 package. |
| `git diff --check` | Passed before this checkpoint. |

The tests cover immutable source capture and storage, receipt/idempotency semantics, native agent capabilities and read-only source confinement, deterministic disposition gates, native report parsing and discovery, command-boundary cancellation, request replay refusal, repeated evaluation identities, evidence/grounding-gated accuracy, complete denominators, unknown-token handling, private exports, language rollups, comparisons, and non-promotable development/generated reports.

## Live integration evidence so far

A real local OpenShell 0.1.3 gateway and SDK were exercised with a digest-pinned Python/pytest image: native create, input transfer, real collection, real test execution, native JUnit retrieval, integrity checks, and identity-aware deletion. A real native Temporal worker executed fine-grained model/source-tool activities with a deterministic `FunctionModel` fixture; native history replay dispatched **zero additional model calls**. These earlier boundary checks passed. Final whole-episode timeout, deployment-queue, and cancellation changes still require a fresh native integration run before they are described as qualified.

Actual inference through the native PydanticAI factory also completed a source-grounded typed assessment with GPT-5 mini, measured provider token presence, and source citations. Small local Qwen profiles were exercised rather than replaced by fabricated responses.

## Preliminary public-development benchmark

An explicitly pinned eight-case OWASP Java/Python source-only development sample was run through the production source-analysis path. Labels and CWE metadata remained evaluator-side; source paths were neutralized by the importer. This is a small public wiring/diagnostic sample, not a held-out effectiveness study, a production-reachability result, or a comparison with published OWASP scanner scores.

| Actual inference profile | Cases | Correct classifications | Usable predictions | Interpretation |
| --- | ---: | ---: | ---: | --- |
| GPT-5 mini, configured OpenAI-compatible endpoint | 8 | 5 | 8 | Three false positives; further model/prompt evaluation is necessary. |
| Qwen 2.5 1.5B, local CPU Ollama | 8 | 0 | 0 | Failed/over-budget structured-output attempts remained explicit unknowns, not invented labels or silent model escalation. |

These figures precede the final evidence-gated reporting refinements. The original private native reports are retained for diagnosis. A frozen-policy rerun is needed for a formal baseline; the development sample is explicitly ineligible for baseline promotion.

## Outstanding validation at this checkpoint

The complete real-model, independent-author, validity-review, OpenShell baseline/candidate, and generated-repair episode is **not yet passing**. Two GPT-5 mini attempts stopped honestly at investigator output validation: `UnexpectedModelBehavior` / `InvestigationPlan` required source citations and both native probe specifications. No workload sandbox was acquired for those attempts and no security finding or repair was claimed. A stronger coding-capable model and targeted native-output diagnostics are prepared for the next check; no successful result is presumed.

The repository-wide legacy regression suite and a fresh final native Temporal replay/cancellation run have not yet been completed for this checkpoint.

## Deployment boundaries

The local Docker/OpenShell profile remains **unqualified**. No all-true qualification certificate was fabricated to produce a conclusive verdict. Qualification configuration is operator attestation bound to the configured runtime identities, not an independently issued or signed runtime proof. Native name-addressed deletion is not an atomic UUID-conditional API, and gateway absence is not independent driver garbage-collection proof.

The implemented evidence/receipt tier is **single-host POSIX content-addressed storage plus SQLite WAL**. Same-domain processes can share that tier; it must not be represented as a multi-host shared Postgres/S3 implementation. Keep an exclusive controller namespace, private evidence/history storage, and immutable worker deployments. See [architecture](newarchitecture.md), [OpenShell operations](openshell.md), [metrics](metrics.md), and [upstream decisions](newupstream-decisions.md).
