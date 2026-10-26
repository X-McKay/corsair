# Domain schemas

Canonical domain contracts are SDK-free, frozen Pydantic models under [`src/corsair/contracts/`](../../src/corsair/contracts/). Import their public names from `corsair.contracts`; the focused source modules are the single authority. This page explains their relationships and intentionally does **not** commit a parallel JSON Schema or copied configuration schema.

```python
from corsair.contracts import InvestigationRequest, Submission
```

Every `Contract` rejects extra fields, is immutable after validation, and disallows non-finite floating-point values. An `Identifier` is 1–80 characters matching `[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}`. A `Digest` is a 64-character lowercase SHA-256 hexadecimal value. Fields validated as safe source paths are normalized relative POSIX paths, not host-absolute paths.

## Generate the current JSON Schema

Generate schemas from the installed models whenever a machine consumer needs them. Do not check the output into a second source-of-truth file.

```bash
uv run --locked python - <<'PY'
import json

from corsair.contracts import (
    AuditResult,
    InvestigationRequest,
    InvestigationResult,
    ProducerDecision,
)

for model in (InvestigationRequest, ProducerDecision, AuditResult, InvestigationResult):
    print(f"# {model.__name__}")
    print(json.dumps(model.model_json_schema(), indent=2, sort_keys=True))
PY
```

Use `Model.model_validate_json(...)` or `Model.model_validate(...)` to validate input, rather than treating the generated schema as an independent validation implementation.

## Source, case, and request

[`sources.py`](../../src/corsair/contracts/sources.py) defines the operator/request-side model lineage:

```text
InvestigationRequest
├── case: Case (corsair.case/1)
│   ├── finding: Finding
│   ├── source: Source
│   ├── fixed_source: Source | null
│   └── recipe: Recipe  # PythonRecipe | PythonCommandSentinel | JavaScriptRecipe | RubyRecipe | JavaRecipe | PerlRecipe | CRecipe, on `kind`
└── budget: Budget
```

- A **finding** is the reported title, description, source file, optional line, and requested claim scope. It is not trusted evidence.
- A **source** names a local source-tree path and may pin its expected snapshot digest. It is a proposed local input, not an admitted archive or a remote checkout.
- A **recipe** is the operator-owned test shape, selected by its `kind` tag. See [Recipes](#recipes). The recipe must bind to the finding's file.
- A **case** combines that finding, source, recipe, optional fixed source, and stable `case_id`. A case describes what to investigate; it has no run budget and no workflow identity.
- An **investigation request** is a case plus a bounded `Budget`. The default budget is bounded in rounds, model/tool calls, output tokens, elapsed time, probe time, tool output, and source handling. `max_output_tokens` caps each model request of both the producer and the auditor; on a thinking model it includes reasoning tokens (see the `Budget` docstring in [`contracts/sources.py`](../../src/corsair/contracts/sources.py)). It is the typed Temporal input for one investigation.

### Recipes

`Case.recipe` is a discriminated union on the stable `kind` tag, following the native `ProducerDecision` pattern; a request that predates the union omits `kind` and resolves to the Python recipe. Each member is one concrete, tested recipe with its own trusted observer and runtime image. Adding a language adds a union member, not a generic adapter.

- **`PythonRecipe`** (`kind: "python.secret_disclosure/1"`, [`sources.py`](../../src/corsair/contracts/sources.py)) binds to one public Python callable and its actual module file. The investigator controls only the `payload_parameter` value; fixed keyword arguments, public fixtures, expected control value, and allowed-exception policy are not agent-editable.
- **`PythonCommandSentinel`** (`kind: "python.command_sentinel/1"`, [`recipes_python.py`](../../src/corsair/contracts/recipes_python.py)) binds to one public Python callable like `PythonRecipe` and shares its fixed-argument, fixture and exception fields. The observed property is whether invoking the callable creates the operator-fixed `sentinel_path` (a non-traversing path under `/work`): the benign input must not, an input reaching command or code execution does (CWE-78, CWE-94). It has no `expected_control`; the control holds when the call returns without creating the sentinel. See the [Python corpus map](corpus-python.md).
- **`JavaScriptRecipe`** (`kind: "javascript.prototype_pollution/1"`, [`recipes_javascript.py`](../../src/corsair/contracts/recipes_javascript.py)) binds to one exported CommonJS `.js` callable. The investigator controls only the model payload, which the trusted driver passes as the final positional argument to `function(*fixed_arguments, payload)`; `module_file`, `function` and the fixed leading arguments are not agent-editable. The observed property is whether invoking the callable adds any enumerable property to `Object.prototype` (CWE-1321); it reads no fixture. See the [JavaScript corpus survey](corpus-javascript.md) for the row it qualifies.
- **`RubyRecipe`** (`kind: "ruby.secret_disclosure/1"`, [`recipes_ruby.py`](../../src/corsair/contracts/recipes_ruby.py)) binds to one public Ruby module/class method (`receiver`, `function`) in a `.rb` file and observes the same secret-disclosure property as `PythonRecipe`: the investigator controls only the `payload_parameter` keyword value; the receiver, method, fixed keyword arguments, public fixtures, expected control value and allowed exception classes are not agent-editable. See the [Ruby corpus survey](corpus-ruby.md).
- **`JavaRecipe`** (`kind: "java.secret_disclosure/1"`, [`recipes_java.py`](../../src/corsair/contracts/recipes_java.py)) binds to one public Java `entry_class.method(String)` compiled from the admitted `source_roots` with `javac` alone and observes the same secret-disclosure property: the investigator controls only the single `String` payload; the entry class, method, compile roots, public fixtures, expected control value and allowed exception classes are not agent-editable. See the [Java corpus survey](corpus-java.md).
- **`PerlRecipe`** (`kind: "perl.html_injection/1"`, [`recipes_perl.py`](../../src/corsair/contracts/recipes_perl.py)) binds to one public Perl sub (`package`, `function`) in a `.pm`/`.pl` module. The investigator controls only the model payload, which the trusted driver passes as the final positional argument to `package::function(@fixed_args, payload)`; `module_file`, `package`, `function`, the fixed leading arguments, the expected benign return, the template markup budget and the allowed-exception substrings are not agent-editable. The observed property is whether the rendered output carries more markup characters (`<`/`>`) than the fixed template, i.e. an injected tag (CWE-79); it reads no fixture. `baseline_markup_chars` is the template's markup count on the benign control: when omitted it is derived from a string `expected_control` (4 for the default `<div class='comment'>hello</div>`), it is required for any non-string `expected_control`, and an explicit value must equal the string control's count, because the control demands both the exact benign return and that count. An adversarial sub that returns `undef` rendered no HTML and holds; undefined output never establishes an injection. See the [Perl corpus survey](corpus-perl.md) for the row it qualifies.
- **`CRecipe`** (`kind: "c.integer_overflow/1"`, [`recipes_c.py`](../../src/corsair/contracts/recipes_c.py)) binds to one C callable of the fixed shape `char *function(const char *buf, unsigned short len)` in a `.c` file. The investigator controls only the integer length (the submission's control and exploit payloads); the fill byte, expected benign length and admitted sanitizer class are not agent-editable. The trusted driver compiles the admitted source plus a fixed harness under AddressSanitizer with gcov coverage; a VIOLATION is admitted only for a sanitizer report of the fixed class in a frame naming the target file, and a plain crash or compile failure is ERROR. It reads no fixture. See the [C corpus survey](corpus-c.md).

`load_investigation_request()` validates request JSON and converts source paths to absolute paths relative to the request file. That is not admission. The local admission adapter later accepts only a non-symlink directory beneath configured `source_root`, snapshots its admitted bytes, and exposes only that immutable snapshot. Current source admission is local; remote SCM checkout is not a present schema or adapter.

## Prepared case, manifest, and artifacts

A **prepared case** is worker-derived after source admission. `PreparedCase` holds the case identity, finding, recipe, source artifact reference, optional fixed-source artifact reference, a bounded source excerpt, a manifest, and `line_provenance`: `declared`, or `recipe_function` when the finding declared no line and trusted prepare code bound it to the recipe function's first body statement (the finding's `line` then holds that derived line), and `target_line`: the line the coverage gate requires, bound in code at prepare from `finding.line` (`null` in records made before line binding, where the kernel uses `finding.line`). It is not an alternate request format.

A **run manifest** (`corsair.manifest/1`) binds a run to its request and configuration digests, producer/auditor prompt digests, immutable image ID, chosen model names, and recorded capabilities. It records run provenance; it is not a mutable settings document and does not carry credentials.

An **artifact reference** has only `sha256`, `size`, and `media_type`. It names immutable bytes in the artifact store; it is not a host path, container handle, or assertion that the referenced bytes prove a security outcome. The store verifies digest and size on reads. Source snapshots, native receipts, operation records, and completed-result references use this mechanism.

## Agent proposals and audit

[`agents.py`](../../src/corsair/contracts/agents.py) is the canonical definition of the native ADK structured outputs:

- A **plan revision** gives a positive `revision`, optional parent revision, objective, up to eight next steps, and a bounded reason. It is a proposal-local revision record, not a Temporal workflow plan or an execution log.
- A **submission** (`corsair.submission/1`) contains a hypothesis, one `PlanRevision`, and exact control/exploit values for the recipe's `payload_parameter`. Each payload can be any JSON value through an explicit union; it is a value for the parameter, not a keyword-argument wrapper unless that parameter itself expects an object. The combined payload encoding is capped at 32 KiB.
- A **producer decision** (`corsair.producer-decision/1`) is the producer's direct native ADK output schema. It is one flat object: `kind` is `proposal`, which requires one unchanged `submission` and forbids `reason`, or `no_grounded_candidate`, which requires a bounded `reason` for abstaining and forbids `submission`. The flat shape lets ADK's `set_model_response` tool declare typed top-level parameters (`submission` is declared `"type": "object"`), so OpenAI-compatible tool-call parsers that decode arguments by parameter type deliver it as an object; a stored decision recorded by the earlier discriminated union has the same JSON and still decodes. Only a proposal reaches trusted evidence collection.
- An **audit result** is the auditor's structured, outcome-blind semantic review: `ACCEPT`, `REJECT`, or `INSUFFICIENT_CONTEXT`, plus a rule and reason. It cannot create native evidence or itself determine the final disposition.

The producer declares `ProducerDecision` directly as its ADK `output_schema`; the auditor similarly declares `AuditResult`. The producer has only `read_file` and `list_files` against an already admitted snapshot. Neither role has a skill loader: each role's packaged procedure is preloaded into its instruction. The auditor has no tools at all, so ADK sends `AuditResult` as the response schema of its single request. A valid structured object is therefore neither a successful target execution nor proof of a vulnerability.

## Observation and evidence

[`evidence.py`](../../src/corsair/contracts/evidence.py) separates raw trusted observations from proposals and conclusions.

An `EvidenceInput` binds one operation to a prepared case, submission, budget, and whether it is the separately requested fixed-source run. Its resulting `Observation` records the operation, source and submission digests, optional control/adversarial `RoleObservation`s, feedback, a raw receipt artifact reference, and independently confirmed cleanup.

A role observation reports one of these **execution outcomes**:

- `PROPERTY_HELD`
- `VIOLATION`
- `INVALID`
- `ERROR`

It also states whether the target actually executed, optional covered lines, reason, and optional native exit code. These are verifier-level facts about one role execution. They are not the final verdict, and an absent/invalid/error observation cannot be converted into a negative security conclusion.

The narrow ports preserve this separation: `SourceSnapshotPort` produces a prepared case from local admission; `InferencePort` produces/audits typed models; `SandboxPort` returns an immutable raw receipt `ArtifactRef`, not a trusted verdict. Docker SDK execution and receipt verification occur outside the agent proposal boundary.

## Results, status, disposition, and fix

[`results.py`](../../src/corsair/contracts/results.py) collects durable results without conflating their meanings:

- A **round result** groups the producer decision/output with its optional native observation and audit output for one numbered round. An explicit no-grounded-candidate abstention ends a newly recorded workflow `INCONCLUSIVE` with no target execution or audit; it does not create negative clearance.
- An **execution status** is operational: `COMPLETED`, `BLOCKED`, `ERROR`, or `CANCELLED`. `COMPLETED` means the workflow reached its result path; it does not mean that a finding was supported.
- A **label** is the kernel's conclusion: `EXPLOIT_DEMONSTRATED`, `COMPONENT_EXPLOIT_DEMONSTRATED`, `EXPLOIT_NOT_DEMONSTRATED`, `INCONCLUSIVE`, `UNABLE_TO_RUN`, or `ERROR`. A single non-demonstrating exploit run, an uncovered target line, a rejected pair, or incomplete evidence remains `INCONCLUSIVE`; `EXPLOIT_NOT_DEMONSTRATED` needs at least two independent coverage-valid sessions. `COMPONENT_EXPLOIT_DEMONSTRATED` is a genuine component-seam differential for an application-scope claim whose application reachability was not established. Claim scope drives the `EXPLOIT_DEMONSTRATED` versus `COMPONENT_EXPLOIT_DEMONSTRATED` split but is also carried separately as result data. See [Data flow](../architecture/data-flow.md#6-verdict-table).
- A **fix status** concerns the separately observed `fixed_source`: `NOT_REQUESTED`, `DEMONSTRATION_BLOCKED`, `NOT_BLOCKED`, or `UNVERIFIED`. `DEMONSTRATION_BLOCKED` means the particular admitted demonstration was blocked while its control held; it is not universal patch correctness. Missing evidence, operational feedback, failed cleanup, or invalid roles leave the fix `UNVERIFIED`.

`InvestigationResult` (`corsair.result/1`) brings these values together with the run and case IDs, reason, scope, optional manifest, rounds, usage-completeness flag, optional fixed observation, and final result artifact reference. A returned result must be read as both a disposition and an execution status.

For batch evaluation, [`evaluation.py`](../../src/corsair/contracts/evaluation.py) defines `BatchRequest` (bounded requests, repeats, concurrency, and batch ID) and `BatchItem` (case/run identity plus artifact or error). The same module holds the evaluator-only frozen-dataset schemas: `Dataset` and `DatasetEntry` (a composed-case manifest and its digest-pinned request/oracle paths) and `Oracle` (a case's acceptable and forbidden dispositions and labels). Their schema is canonical here, but oracle values are read only by [`corsair.evaluation`](../../src/corsair/evaluation/datasets.py) and never enter `BatchRequest` or any agent, tool or workflow input; evaluation labels and scores are owned outside the workflow-input contract.

The [Python API reference](api.md) shows how these models enter and leave a Temporal workflow. For concise terminology, see the [glossary](glossary.md); for current schema-related work, see [current plans](../plans/README.md).

## Execution intent compatibility

New executions bind the complete capability manifest digest in `corsair.evidence-intent/2`. A completed or unknown v1 operation is not blindly migrated or re-executed under the changed policy: its immutable claim is retained and a mismatched reconciliation is explicit. The packaged risk assessment contributes to the declared capability identity; configuration settings alone are not the complete runtime identity.
