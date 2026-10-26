# Integration guide

Corsair exposes a typed Python submission API over native Temporal workflows. It is not an HTTP service, webhook endpoint, remote-forge adapter, or a second agent runtime. A caller still needs a reachable Temporal service, a separately running Corsair worker, the reviewed Docker environment, and a shared artifact root where offline results will be read.

## Use request-relative local sources

Use `load_investigation_request` when reading a request JSON file. It validates the canonical `InvestigationRequest` and turns `case.source.path` (and `fixed_source.path`, when present) into absolute paths relative to that JSON file. Do not reinterpret those strings relative to the process working directory, pre-resolve untrusted symlinks, or replace the admitted local-source boundary with a remote checkout.

```python
from pathlib import Path

from corsair.entrypoints.requests import load_investigation_request

request = load_investigation_request(Path("requests/case.json"))
```

The resolved paths must remain under the operator-configured `source_root`. Request content does not carry provider credentials, evaluator labels, or an arbitrary host path capability.

## Submit one investigation

The implemented public function is:

```python
async def start_investigation(
    client: Client,
    request: InvestigationRequest,
    settings: Settings,
    *,
    run_id: str,
) -> WorkflowHandle[InvestigationWorkflow, InvestigationResult]:
    ...
```

`connect(settings)` is the native Temporal client helper. It connects to the address and namespace selected by `Settings` and installs the Pydantic data converter; it neither starts a worker nor adds authentication or a retry layer. `wait_for_result(handle)` only observes the existing workflow and never cancels or schedules work.

```python
import asyncio
from pathlib import Path

from corsair.adapters.temporal.client import connect, wait_for_result
from corsair.entrypoints.api import start_investigation
from corsair.entrypoints.requests import load_investigation_request
from corsair.settings import load_settings


async def main() -> None:
    settings = load_settings(Path(".state/settings.json"))
    request = load_investigation_request(Path("requests/case.json"))
    client = await connect(settings)

    handle = await start_investigation(
        client,
        request,
        settings,
        run_id="case-20261025-01",
    )
    result = await wait_for_result(handle)
    print(result.model_dump_json(indent=2))


asyncio.run(main())
```

`start_investigation` uses `settings.task_queue`, applies the request's elapsed-time budget to the workflow execution timeout, and rejects a duplicate workflow identity. Generate a new identity for a new request rather than retrying a possibly uncertain operation under the same ID. The returned `InvestigationResult` and its immutable artifact reference are the result boundary; a submitted handle is not evidence of completed target execution.

For live state without waiting, query the workflow's implemented status method:

```python
from corsair.workflows.investigation import InvestigationWorkflow

status = await handle.query(InvestigationWorkflow.status)
# {"phase": ..., "round": ...}
```

## Submit a finite evaluation batch

The batch entry point is likewise typed:

```python
async def start_evaluation(
    client: Client,
    request: BatchRequest,
    settings: Settings,
) -> WorkflowHandle[EvaluationWorkflow, list[BatchItem]]:
    ...
```

Construct `BatchRequest` from canonical `InvestigationRequest` objects. It accepts 1–64 requests, 1–8 repeats, and 1–8 concurrent child workflows, with a 1 MB serialized request bound. The workflow input contains cases only; evaluator-owned labels and scoring remain outside it.

```python
from corsair.contracts import BatchRequest
from corsair.entrypoints.api import start_evaluation

batch = BatchRequest(
    batch_id="development-batch-20261025",
    requests=[request],
    repeats=3,
    concurrency=2,
)
handle = await start_evaluation(client, batch, settings)
items = await wait_for_result(handle)
```

The result is a list of `BatchItem` receipts with each child run identity and, when committed, its result artifact. This API does not invent an oracle, score a batch, or repair unavailable artifacts. Use the `corsair eval`/`corsair rescore` commands when working from a frozen evaluator dataset and its external oracle set.

## Admit a scanner finding

An upstream scanner's `ScanReport` ([`contracts/intake.py`](../../src/corsair/contracts/intake.py)) is read with `load_scan_report` and one finding is mapped with `finding_from_scanner` ([`entrypoints/requests.py`](../../src/corsair/entrypoints/requests.py)); the operator still supplies the `Case` around it: its source, and the recipe whose `module_file` is the finding's `file`. Everything the scanner says is untrusted and reaches neither the verdict nor a model prompt; see [data flow](../architecture/data-flow.md).

A scanner may report a function but no `line`. Intake keeps the line absent; it never reads a line or a function name out of the description. During `prepare`, trusted code binds the line from the operator-owned recipe instead: when `recipe.function` is exactly one undecorated, synchronous, top-level `def` in the admitted module, the line becomes that function's first executable body statement (a leading docstring, `global`/`nonlocal` and bare annotations are skipped). The `def` line is never used, because importing the module executes it whether or not the call reaches the function. The prepared case records `line_provenance: recipe_function`, the producer and auditor packets state that the line was derived from that function, and `corsair inspect --evidence` shows the target line with "derived from recipe function". The derived line then faces the same exact-line coverage gates as a declared one. When the binding is not certain (a decorated, nested, re-bound, star-imported or coroutine callable, a body that starts on the `def` line, an unparseable module), the finding stays line-less and the case is `UNABLE_TO_RUN` before any model call, as before. Example: [`python-reader-no-line.json`](../../evals/fixtures/scan_reports/python-reader-no-line.json).

### Dry run a scan report: `corsair intake`

Before submitting anything, `corsair intake REPORT --source-root DIR --recipe-template FILE` ([CLI reference](../reference/cli.md#intake-report---source-root-dir---recipe-template-file)) shows which findings of a report would become admissible requests and why the rest would not. For each finding it builds the candidate request with `request_from_scanner` ([`adapters/scm/requests.py`](../../src/corsair/adapters/scm/requests.py), re-exported with `finding_from_scanner` from `entrypoints/requests.py`): the operator's recipe template (a `PythonRecipe` without `module_file`, read with `load_recipe_template`) bound to the finding's `file`, the admitted source, and the finding as `finding_from_scanner` maps it. It then runs, over the admitted snapshot, the same line binding (`bind_target_line`) and pre-model `target_binding` check the prepare activity runs. No model, Temporal or container is involved, and nothing comes from the finding's description. The assessment is pure code in [`evaluation/intake.py`](../../src/corsair/evaluation/intake.py); its only I/O is the real snapshot admission into a scratch store.

A line-less finding whose recipe function is one plain top-level `def` is `admissible:recipe_function`, with the line prepare will derive; the candidate request itself stays line-less, so prepare derives and records it. A finding the scanner points at a file outside the tree, in another language or absent from the snapshot, at a function the template does not name, or at a line beyond the module, is `blocked` with the reason. The JSON receipt carries each admissible finding's complete request, with the snapshot digest pinned, ready to save and submit with `corsair investigate` (its absolute `source.path` must stay under the worker's `source_root`).

Intake quality is measured on a frozen dataset: [`evals/datasets/intake.json`](../../evals/datasets/intake.json) pairs the scan reports under [`evals/fixtures/scan_reports`](../../evals/fixtures/scan_reports/) with a synthetic source tree, a recipe template and an evaluator-only oracle of each finding's expected outcome. `just eval-intake evals/datasets/intake.json` scores it into a report that `corsair report` and `corsair compare` read, so a change to intake, binding or the fixtures shows up as a per-finding regression. On the current tree it scores 12 of 12 findings: 3 admissible (1 with a derived line) and 9 blocked across 8 reasons.

## Boundaries to preserve

The client helpers are deliberately small: they use the Temporal SDK, do not import worker or agent composition, and do not provide automatic retries around submissions or observation. Provider credentials stay in the worker environment; source and artifact paths remain operator settings. The only implemented source adapter is local snapshot admission, and the only implemented evidence sandbox uses the Docker SDK. Do not build an integration on assumed remote SCM, Bedrock, HTTP, or generic provider endpoints.

For command contracts, including inspection and cancellation, see the [CLI reference](../reference/cli.md). For configuration ownership and credential handling, see the [configuration guide](configuration.md). Current integration limits and planned work are in the [current plans](../plans/README.md).
