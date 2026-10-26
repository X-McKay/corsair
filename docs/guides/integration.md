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

## Boundaries to preserve

The client helpers are deliberately small: they use the Temporal SDK, do not import worker or agent composition, and do not provide automatic retries around submissions or observation. Provider credentials stay in the worker environment; source and artifact paths remain operator settings. The only implemented source adapter is local snapshot admission, and the only implemented evidence sandbox uses the Docker SDK. Do not build an integration on assumed remote SCM, Bedrock, HTTP, or generic provider endpoints.

For command contracts, including inspection and cancellation, see the [CLI reference](../reference/cli.md). For configuration ownership and credential handling, see the [configuration guide](configuration.md). Current integration limits and planned work are in the [current plans](../plans/README.md).
