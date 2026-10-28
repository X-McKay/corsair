# Python API reference

## Current intake-gated API

`start_investigation(client, request, settings, run_id=...)` accepts `IssueInvestigationRequest` and returns a handle to `corsair.issue-investigation.v4`, whose result is `IssueInvestigationResult`. `start_issue_investigation` is the explicit equivalent. Canonical request/result definitions are in [`contracts/pipeline.py`](../../src/corsair/contracts/pipeline.py). `load_issue_investigation_request` loads bounded v4 JSON and anchors source paths to its file. [The guide](../guides/investigations.md) describes the categorical gates, shared budget, pinned image handoff and incomplete outcomes.

`start_execution` and `load_execution_request` retain explicit v3 diagnostics using `ExecutionRequest`/`ExecutionResult`; passing that request to `start_investigation` raises an error. Standalone `start_intake` does not schedule execution. Explicit legacy `InvestigationRequest` objects retain the historical diagnostic path below.

`TestPlan` is the producer's native output schema; `PlanAudit` is the auditor's. Trusted `ProcessObservation` records actual command exits/output and cleanup, with `UNRESOLVED` security assessment in the result. Canonical contracts are defined once; role-local contracts re-export those same objects.

## Historical v1/v2 reference

The remaining material describes retained fixed-observer diagnostics, immutable old results and frozen evaluation inputs. Normal CLI investigations use the v4 intake-gated models above.

Corsair exposes a small, typed **asynchronous Python API** for submitting and observing native Temporal workflows. It is not an HTTP service, web API, or an alternate agent/workflow implementation. The CLI uses the same submission functions. For the data models passed here, see the [domain schemas](schemas.md); for operator-owned connection and worker configuration, see [configuration](configuration.md).

## Public functions

Import the functions from their defining modules:

```python
from corsair.adapters.temporal.client import connect, wait_for_result
from corsair.entrypoints.api import start_evaluation, start_investigation
from corsair.entrypoints.requests import load_investigation_request
from corsair.settings import Settings, load_settings
```

The implemented signatures are:

```python
async def connect(settings: Settings) -> Client: ...

async def start_investigation(
    client: Client,
    request: InvestigationRequest,
    settings: Settings,
    *,
    run_id: str,
) -> WorkflowHandle[InvestigationWorkflow, InvestigationResult]: ...

async def start_evaluation(
    client: Client,
    request: BatchRequest,
    settings: Settings,
) -> WorkflowHandle[EvaluationWorkflow, list[BatchItem]]: ...

async def wait_for_result[T](handle: WorkflowHandle[Any, T]) -> T: ...


def load_investigation_request(path: Path) -> InvestigationRequest: ...
```

`connect()` makes a native Temporal SDK connection to `settings.temporal_address` and `settings.temporal_namespace` with Corsair's Pydantic data converter. It has a 10-second local connection timeout. `start_investigation()` and `start_evaluation()` submit workflows to `settings.task_queue`; neither starts a worker nor composes an ADK agent in the client process.

## Complete investigation example

Run this from the repository root after configuring a Temporal service and a worker with compatible settings. Loading settings and a request is synchronous; connecting, submitting, and waiting are all awaited.

```python
import asyncio
from pathlib import Path

from corsair.adapters.temporal.client import connect, wait_for_result
from corsair.entrypoints.api import start_investigation
from corsair.entrypoints.requests import load_investigation_request
from corsair.settings import load_settings


async def main() -> None:
    settings = load_settings(Path(".state/settings.json"))
    request = load_investigation_request(
        Path("evals/fixtures/case01/request.json")
    )

    client = await connect(settings)
    handle = await start_investigation(
        client,
        request,
        settings,
        run_id="case01-api-20261025",
    )

    # Submission acceptance is not workflow completion.
    result = await wait_for_result(handle)
    print(result.model_dump_json(indent=2))


asyncio.run(main())
```

`await start_investigation(...)` returns once Temporal accepts the start request and supplies a workflow handle. It does **not** return an `InvestigationResult`. `await wait_for_result(handle)` observes that handle until it is no longer running and then awaits its native result. This helper only observes; it does not cancel, schedule, or retry durable work. A caller that needs only the submission identity may retain the handle and omit the final await.

`start_evaluation()` follows the same pattern. Its identity is `BatchRequest.batch_id`, and its completed value is `list[BatchItem]`:

```python
handle = await start_evaluation(client, batch_request, settings)
items = await wait_for_result(handle)
```

## Run identity and duplicate handling

An investigation run ID is separate from `Case.case_id`. The API validates `run_id` as the canonical `Identifier`: 1–80 ASCII characters matching `[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}`. A batch ID has the same identifier form and must also leave room for child IDs.

Investigation and evaluation starts set Temporal's conflict policy to `FAIL` and reuse policy to `REJECT_DUPLICATE`. Consequently, a duplicate workflow identity is rejected by the awaited native start operation; it is not treated as an idempotent lookup, attached to the prior run, or restarted. Choose a new run ID for a new attempt. To observe an existing workflow, keep or reacquire its Temporal handle through an appropriate client workflow rather than calling the start function again.

The investigation execution timeout is derived from the request: `request.budget.max_elapsed_seconds + 120` seconds. The API does not add an application retry layer around Temporal submission or execution.

## Settings, request files, and local source admission

Pass the same `Settings` value to `connect()` and the start function. At minimum, client and worker must agree on `temporal_address`, `temporal_namespace`, and `task_queue`. They also need access to the same `artifact_root` for committed results and immutable evidence; Temporal history does not restore a separate lost artifact filesystem. The [configuration reference](configuration.md) lists the current fields and defaults.

`load_investigation_request(path)` validates the JSON as an `InvestigationRequest`. It then makes `case.source.path` and an optional `case.fixed_source.path` absolute relative to the request file's parent, deliberately without resolving a potentially untrusted source symlink. This is client-side path spelling only, not source admission.

Admission occurs in the worker through the local source-snapshot boundary. The requested source must be a directory under `Settings.source_root`; the trusted root and every admitted path component are checked without following symbolic links. The worker snapshots accepted bytes into an immutable artifact before the producer sees source content or the sandbox mounts it. Remote SCM checkout is not an implemented API. See [schemas: source and prepared case](schemas.md#source-case-and-request) for the model distinction and the [pilot runbook](../operations/runbooks/pilot.md) for the operator procedure.

## Failure and cancellation boundaries

Pydantic validation errors from settings, request loading, or run-ID validation happen before a normal workflow start. Temporal connection, start, and result errors propagate through their awaited SDK calls; the Python API does not translate them into a synthetic result or silently retry them.

Cancelling a task that is awaiting `wait_for_result()` cancels that local await, not the remote workflow. Request durable cancellation explicitly through the supported operational path, then inspect the final workflow state and immutable artifacts. A completed result can still contain an operational `ExecutionStatus` such as `BLOCKED`, `ERROR`, or `CANCELLED`; successful receipt of a Python value is not a security verdict. The distinctions are defined in the [schema reference](schemas.md#results-status-disposition-and-fix).

For current documented limitations and planned work, see [current plans](../plans/README.md).
