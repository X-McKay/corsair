# Language recipes and qualification

Corsair admits an operator-owned secret-disclosure recipe, not a general language runtime. A recipe fixes its source entry point, public control, private-fixture observation, allowed exceptions, trusted image, and assertions. The producer supplies **JSON data only**; it does not supply test code, a build command, or a package manifest.

Python remains the established recipe family. Node and Java now have checked-in, recipe-specific native observers, but their current native and whole-system requalification is still in progress. The [PLAN-0127 record](../plans/archive/plans/PLAN-0127-outcomes-node-java.md) is authoritative for commands actually run, their results, and remaining gates.

## Narrow recipe ABIs

| Recipe kind | Admitted entry point | Model-controlled value | Excluded from this ABI |
| --- | --- | --- | --- |
| `python.secret_disclosure/1` | Public function in one `.py` file. | One named JSON `payload_parameter`; `fixed_kwargs` stay operator-fixed. | Target dependency installation and host import/execution. |
| `javascript.secret_disclosure/1` | Named public ESM export in one dependency-free `.mjs` file. | One JSON value inserted into positional `fixed_args` at `payload_index`. | CommonJS, `.js`, TypeScript, target package installation, and target build scripts. |
| `java.secret_disclosure/1` | Public static `String` method on the named public class in one `.java` file. Every argument is `String`. | One inserted string among operator-fixed string arguments. | Target dependencies, Maven/Gradle or other target build scripts, and annotation processing. |

All three classes are canonical Pydantic contracts in [`contracts/sources.py`](../../src/corsair/contracts/sources.py). A `Case` uses their discriminated `kind` union and requires `finding.file == recipe.module_file`. Paths are relative POSIX source paths. Request validation does not admit or execute source.

`JavaScriptRecipe` accepts only the Pydantic literal exception names `Error`, `TypeError`, and `RangeError`; they are distinct when present. Its payload and fixed arguments are JSON values. `JavaRecipe` accepts only qualified Java exception names. Its `fixed_args`, expected control, and inserted payload are strings; the class's final segment must match the `.java` filename.

## Implemented native observers

The dependency-free Node image contains a checked-in driver and fixed `node:test` probe. The driver invokes Node's native test runner with its JUnit reporter and LCOV coverage reporter, then projects the reports into one `corsair.driver/1` receipt. The receipt records the native exit, projected test status, and covered source lines needed by the evidence verifier.

The Java image is a pinned JDK observer. It contains pinned JUnit Platform, JaCoCo, and Jackson observer dependencies; the target itself receives no dependencies. Its driver compiles only the admitted source file with `javac -proc:none`, runs the fixed JUnit Platform probe, obtains JaCoCo XML coverage, and projects the native reports into the same receipt shape. No target build script or annotation processor is used.

The observers are implemented evidence boundaries for these exact recipes. Native reports, coverage, cleanup, audit, and the remaining composed gates still determine whether a submitted result is usable; a checked-in image or contract does not by itself qualify a run.

## Request examples

These are request data, not commands to execute target source. Relative `source.path` is resolved relative to the request JSON before source admission checks it against `Settings.source_root`.

### Node ESM request

```json
{
  "case": {
    "case_id": "node-secret-demo",
    "finding": {
      "title": "Path traversal may disclose a private fixture",
      "description": "Component-level demonstration request.",
      "file": "src/reader.mjs",
      "line": 7,
      "claim_scope": "component"
    },
    "source": {"path": "./demo-node"},
    "recipe": {
      "kind": "javascript.secret_disclosure/1",
      "module_file": "src/reader.mjs",
      "function": "readFileAt",
      "fixed_args": ["/fixtures/allowed"],
      "payload_index": 1,
      "public_files": {"hello.txt": "hello"},
      "expected_control": "hello",
      "allowed_exceptions": ["RangeError"]
    }
  }
}
```

### Java request

```json
{
  "case": {
    "case_id": "java-secret-demo",
    "finding": {
      "title": "Path traversal may disclose a private fixture",
      "description": "Component-level demonstration request.",
      "file": "src/Reader.java",
      "line": 7,
      "claim_scope": "component"
    },
    "source": {"path": "./demo-java"},
    "recipe": {
      "kind": "java.secret_disclosure/1",
      "module_file": "src/Reader.java",
      "class_name": "Reader",
      "function": "readFileAt",
      "fixed_args": ["/fixtures/allowed"],
      "payload_index": 1,
      "public_files": {"hello.txt": "hello"},
      "expected_control": "hello",
      "allowed_exceptions": []
    }
  }
}
```

Validate a draft through the installed canonical model; this validates data only:

```python
from pathlib import Path

from corsair.contracts import InvestigationRequest

request = InvestigationRequest.model_validate_json(Path("request.json").read_bytes())
print(request.case.recipe.kind)
```

## Images, tasks, and `doctor`

`Settings.image_for_recipe()` selects `image` for Python, `node_image` for Node, and `java_image` for Java. A selected tag is resolved to an immutable local Docker image ID for the manifest and receipt; a tag alone is not an execution record.

```bash
# Build the three reviewed observer images.
just images

# Build one observer image with an optional literal tag.
just images-python 'corsair-python:0.1'
just images-node 'corsair-node:review-candidate'
just images-java 'corsair-java:review-candidate'
```

`corsair doctor --settings PATH` remains a baseline Python infrastructure preflight. It checks the configured Python `image` with Docker and Temporal infrastructure; it does not resolve a request's selected recipe image, execute a target, validate native evidence, or qualify a recipe.

## Completed paired outcomes

`assessment_outcome` is optional only on new `corsair.result/2` records and is separate from legacy `disposition`, `execution_status`, and fixed-source status.

| Completed outcome | Required evidence |
| --- | --- |
| `DEMONSTRATED` | `COMPLETED` execution with a healthy control and a valid, actually executed adversarial disclosure. |
| `NOT_DEMONSTRATED` | `COMPLETED` execution after the entire diverse finite protocol completes with valid healthy controls and actually executed held adversarial attempts. |

Both require validated immutable receipt and coverage, confirmed cleanup, and an accepted independent audit. A repeated candidate, failed or rejected audit, missing/invalid evidence, provider or execution error, timeout, unavailable service, or uncertain cleanup leaves the outcome unresolved (`null`). Producer follow-up feedback is mechanical—for example, request a new distinct source-grounded candidate—and does not carry evidence labels or outcomes.

`NOT_DEMONSTRATED` is limited to the submitted bounded protocol. It is not a `REFUTED` result, an application-wide conclusion, or a fixed-source conclusion. A fixed-source observation remains a separate narrow `FixStatus` check.

## Frozen cohorts and status

Historical `corsair.result/1` records, legacy oracles, and their frozen inputs retain their original bytes and interpretation. New `corsair.result/2` assessments use separate `corsair.assessment-oracle/1` datasets. Node and Java cohorts are separate from preserved Python history and from each other.

See [extensions](extensions.md), [testing](../development/testing.md), [evaluations](../agents/evaluations.md), and [PLAN-0127](../plans/archive/plans/PLAN-0127-outcomes-node-java.md) for the exact implemented boundary, the passing physical-Mac native gates, unrun Linux gates, and still-unpromoted live-model results.
