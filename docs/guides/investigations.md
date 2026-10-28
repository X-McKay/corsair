# Intake-gated investigations

Normal investigations use `corsair.issue-investigation-request/4`: native Temporal runs intake, stops unsupported or out-of-scope issues, and otherwise starts the recipe-free v3 investigation with the selected immutable image. A producer proposes bounded tests, an outcome-blind auditor reviews them, and trusted code executes accepted commands in Docker.

## Start from scanner JSON or an issue reference

Configure the model provider, admitted `source_root`, shared `artifact_root`, reviewed images and ordinary Temporal worker as described in [configuration](configuration.md). Build the separate inspection reader with `just images-intake`. Images must already exist locally; neither intake nor execution pulls or builds target images.

```bash
uv run --locked corsair investigate --json /operator/issue.json \
  --source /operator/repository --settings /operator/settings.json \
  --wait --format json
```

Use `--issue OWNER/REPO#NUMBER` instead of `--json` for a configured GitHub repository. Scanner JSON may have varied structure; intake normalizes one finding to the canonical `Issue`. Ambiguous or insufficient input stops with `NEEDS_INPUT`. Standalone [intake](../agents/intake.md) remains available for inspection without scheduling investigation.

Only a completed `in_scope_supported` result proceeds. Other gates return categorical `OUT_OF_SCOPE`, `UNSUPPORTED`, `NEEDS_INPUT` or `INTAKE_ERROR` stops before producer scheduling. Unsupported details remain in the intake decision's missing requirements and reason codes. The handoff binds committed intake provenance, normalized issue, source digest, current configuration and exact inventory image metadata/immutable ID. Changed source, unavailable images or invalid provenance fail explicitly before production; there is no default-image fallback.

The image selected by intake reaches the producer packet and Docker executor. ADK reasoning runs in worker activities; generated tests and target code run inside the selected Docker image. Source inspection uses its separate reviewed reader image. Intake does not authorize new mounts, networking or privileges.

## Typed request and API

A request file supplies the root budget once under `intake`; it has no execution image field. Sources are relative to the request file and retain secure admission checks.

```python
from corsair.contracts import IssueInvestigationRequest, Source
from corsair.contracts.intake import IntakeRequest, JsonIssueInput
from corsair.entrypoints.api import start_investigation

request = IssueInvestigationRequest(
    case_id="reported-issue",
    intake=IntakeRequest(
        input=JsonIssueInput(payload={"title": "Traversal", "file": "reader.py"}),
        source=Source(path="/operator/repository"),
    ),
)
handle = await start_investigation(client, request, settings, run_id="reported-issue-run")
result = await handle.result()
```

`corsair investigate /operator/request.json --wait` accepts this v4 request. `start_issue_investigation` is the explicit typed equivalent. The parent workflow is `corsair.issue-investigation.v4`; it invokes `corsair.intake` and, when admitted, `corsair.investigation.v3`. Offline and online `inspect` understand the aggregate result and child artifact references.

The parent deducts intake model calls, tool calls and mandatory inspection reads from the shared execution budget and wall-clock deadline. Insufficient remaining budget returns `BUDGET_EXHAUSTED`. Child failures or cancellation retain explicit incomplete categories and unknown usage. Native cancellation waits for child cancellation and bounded cleanup; this does not establish host-loss recovery.

`IssueInvestigationResult.status` is `stopped`, `investigation_finished` or `incomplete`. `investigation_finished` means a recorded execution child returned; inspect `execution_outcome` and the child artifact for success/failure/error. The parent never turns process success into a vulnerability conclusion.

For explicit diagnostics, `corsair investigate /operator/execution-v3.json --direct --wait` and `start_execution` accept the existing `ExecutionRequest`. This bypasses intake and still validates source and image admission. Passing an execution request to `start_investigation` is rejected with guidance to use the explicit diagnostic API.

## Execution and results

The workflow also caps aggregate serialized plans at 750,000 bytes and result envelopes at 1,000,000 bytes to leave headroom below Temporal’s default payload ceiling. A plan that exceeds remaining aggregate capacity is retained as an immutable proposal artifact with an explicit `RESULT_SIZE_LIMIT`; it is not executed. Canonical limits and exact fields live in [`contracts/execution.py`](../../src/corsair/contracts/execution.py). A plan contains a hypothesis, revision, files, commands with explicit argv/cwd/timeouts, grounded locations and expected process exits. Source is mounted read-only at `/source`; files and commands use bounded writable `/work` and `/tmp`. Unchanged source copies for compilation are permitted. Their existence does not prove the test exercised the admitted source.

The executor is non-root, disables network, drops capabilities, limits CPU/memory/PIDs/time and bounds stdout/stderr before storage. Reviewed execution images need `/bin/sh`, `sleep` and `tar` plus their declared language tools. Test archives enter through fixed in-container `tar` over Docker SDK stdin; target and generated test code never run on the host. No model-owned environment, mounts, credentials, socket or permission settings are admitted. Cancellation waits for the bounded operation and cleanup reconciliation; this is not an instant-stop or host-loss continuation guarantee.

`SUCCEEDED` means actual completed process exits matched the plan's expected exits and cleanup was confirmed. `FAILED` means the exits differed. `ERROR` and `INCOMPLETE` preserve operational uncertainty, missing output, deadlines, rejected audits and exhausted budgets in their result/round fields. Native process receipts bind the admitted request, source, image, plan and command identities. Unknown operation/container ownership produces an immutable refusal with cleanup unconfirmed, separate from a completed execution commitment. Generated output and reports remain untrusted content.

Security assessment is always `UNRESOLVED` in this initial v3 capability. Accepted audit plus successful execution is reproduction material for review, not an independent vulnerability oracle. Failed reproduction never grants clearance. Optional fixed source runs the exact same accepted plan in a fresh container and records a process comparison; it does not establish general patch effectiveness.

## Historical compatibility and evaluation

Legacy v1/v2 schemas, observer drivers, recorded workflow names and frozen evaluations remain for decoding, replay and explicit historical diagnostics. Normal CLI `investigate` requires intake input or a v4 request; `--direct` accepts only v3; `verify`, `eval` and `rescore` retain their documented historical formats. Explicit historical request objects in the Python API use the old diagnostic path. Resuming old in-flight workflows across this migration is unqualified.

The [candidate role cohort](../../evals/datasets/execution-roles.json) tests producer structure/source references and exact auditor categories independently through genuine ADK. It is not human-reviewed or held out. Producer structural checks cannot establish test semantics. Live-role results, real Docker conformance, Temporal replay and a full live chain are separate gates. See [current work](../plans/README.md) for actual results and failures.
