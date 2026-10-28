# Domain schemas

## Current investigation schemas

Normal investigations use `IssueInvestigationRequest` and `IssueInvestigationResult` from `corsair.contracts`, defined in [`contracts/pipeline.py`](../../src/corsair/contracts/pipeline.py). The request nests intake input/source/budget; the parent derives its execution image from a supported committed intake result. `start_investigation` and `load_issue_investigation_request` use this v4 boundary. Explicit `start_execution`/`--direct` retains v3 `ExecutionRequest` diagnostics. [The guide](../guides/investigations.md) explains the categorical gates and result meanings.

`TestPlan` is the producer's native output schema; `PlanAudit` is the auditor's. Trusted `ProcessObservation` records actual command exits/output and cleanup, with `UNRESOLVED` security assessment in the result. Canonical contracts are defined once; role-local contracts re-export those same objects.

## Historical v1/v2 reference

The remaining material describes retained fixed-observer diagnostics, immutable old results and frozen evaluation inputs. Normal CLI investigations use the v4 intake-gated models above.

Canonical domain contracts are SDK-free, frozen Pydantic models under [`src/corsair/contracts/`](../../src/corsair/contracts/). Import public names from `corsair.contracts`; this page explains relationships rather than maintaining a parallel schema.

```python
from corsair.contracts import InvestigationRequest, JavaRecipe, JavaScriptRecipe, PythonRecipe
```

Every `Contract` rejects extra fields, is immutable after validation, and disallows non-finite floating-point values. `Identifier` is 1–80 characters matching `[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}`. `Digest` is a 64-character lowercase SHA-256 value. Safe source paths are normalized relative POSIX paths, never host-absolute paths.

## Generate the current JSON Schema

Generate machine-consumable schema from installed models; do not check generated output in as another source of truth.

```bash
uv run --locked python - <<'PY'
import json

from corsair.contracts import AuditResult, InvestigationRequest, InvestigationResult, ProducerDecision

for model in (InvestigationRequest, ProducerDecision, AuditResult, InvestigationResult):
    print(f"# {model.__name__}")
    print(json.dumps(model.model_json_schema(), indent=2, sort_keys=True))
PY
```

## Source, case, and request

```text
InvestigationRequest
├── case: Case (corsair.case/1)
│   ├── finding: Finding
│   ├── source: Source
│   ├── fixed_source: Source | null
│   └── recipe: PythonRecipe | JavaScriptRecipe | JavaRecipe
└── budget: Budget
```

A finding is a claim, source is a proposed local tree, and recipe is the operator-owned test shape. `Case` binds `recipe.module_file` to `finding.file`; request validation does not admit or run the tree. `Budget` bounds rounds, agent/tool calls, output, elapsed/probe time, and source handling.

| Class / kind | Recipe-specific fields and boundary |
| --- | --- |
| `PythonRecipe` / `python.secret_disclosure/1` | `.py` module, public function, public payload parameter, JSON fixed kwargs, fixtures, expected control, and qualified exception names. Missing `kind` is accepted only for legacy Python input. |
| `JavaScriptRecipe` / `javascript.secret_disclosure/1` | Explicit `.mjs` ESM module, public ASCII export, JSON `fixed_args`, inserted JSON payload, fixtures, and JSON expected control. `allowed_exceptions` contains only the Pydantic literals `Error`, `TypeError`, and `RangeError`. |
| `JavaRecipe` / `java.secret_disclosure/1` | `.java` module matching the final segment of qualified `class_name`, public ASCII method, string `fixed_args`, inserted string payload, string expected control, fixtures, and qualified Java exception names. The method ABI is public static `String` with `String` arguments. |

The common positional fields permit at most 16 fixed values. `payload_index` inserts without replacing fixed arguments. Target dependency resolution, target build scripts, and annotation processing are not recipe fields or behaviors. `load_investigation_request()` resolves source paths relative to request JSON, after which local source admission makes the immutable snapshot.

## Prepared case, manifest, and artifacts

A `PreparedCase` is worker-derived after admission. It carries the discriminated recipe, admitted source artifact, bounded source excerpt, optional fixed-source artifact, and manifest. `RunManifest` binds request/configuration digests, producer/auditor prompt digests, resolved immutable image ID, model names, and capabilities. `Settings.image_for_recipe()` selects the configured tag; the manifest records its resolved local ID.

An `ArtifactRef` has `sha256`, `size`, and `media_type`; it names immutable artifact-store bytes, not a host path or evidence conclusion.

## Agent proposals and observations

`ProducerDecision` is the producer's native ADK output: either a proposal carrying one `Submission` or a bounded abstention. `AuditResult` is outcome-blind semantic review. The producer declares `ProducerDecision` and the auditor `AuditResult` directly as native schemas. Neither model output is evidence.

`Observation` binds an operation/source/submission digest to control/adversarial `RoleObservation`s, feedback, evidence artifact, and independent cleanup confirmation. Roles report `PROPERTY_HELD`, `VIOLATION`, `INVALID`, or `ERROR`, plus execution, coverage, diagnostic, and native-exit facts. `SandboxPort` returns the immutable raw receipt; trusted verifier and policy code process it outside the proposal boundary.

## Results status disposition and fix

`InvestigationResult` permits `corsair.result/1` and `corsair.result/2`:

- `ExecutionStatus` is operational: `COMPLETED`, `BLOCKED`, `ERROR`, or `CANCELLED`.
- Legacy `Disposition` is `SUPPORTED`, `REFUTED`, `CONDITIONAL`, or `INCONCLUSIVE`. Result/2 rejects `REFUTED`; preserved result/1 bytes keep their original wire shape.
- `AssessmentOutcome` is optional only on result/2: `DEMONSTRATED` or `NOT_DEMONSTRATED`. A non-null assessment outcome requires `COMPLETED` execution.
- `FixStatus` concerns a separately observed fixed source.

`DEMONSTRATED` requires a healthy control and valid actually executed adversarial disclosure. `NOT_DEMONSTRATED` requires the entire diverse finite protocol to complete with healthy controls and valid actually executed held adversarial attempts. Both also require accepted audit, receipt/coverage validation, and confirmed cleanup. Errors, audit rejection, repeated candidates, missing evidence, unavailable services, and uncertain cleanup leave the outcome `null`.

The external scorer revalidates the exact immutable final result committed as `result.{run_id}`. For the negative outcome it requires each retained round to validate as the expected held pair with its expected operation identity. Legacy and assessment oracles use distinct datasets, and frozen historical records are not relabelled. See [evaluations](../agents/evaluations.md), [language recipes](../guides/languages.md), and [PLAN-0127](../plans/archive/plans/PLAN-0127-outcomes-node-java.md) for the current evidence status.

## Intake-gated aggregate

[`IssueInvestigationRequest` and `IssueInvestigationResult`](../../src/corsair/contracts/pipeline.py) are the canonical v4 normal investigation boundary. The request nests one `IntakeRequest` and optional fixed source; the selected image is derived from supported intake. The result retains categorical stops, the intake result, committed execution artifact reference/outcome and aggregate usage completeness. See [the investigation guide](../guides/investigations.md).
