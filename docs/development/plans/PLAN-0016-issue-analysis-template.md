---
id: PLAN-0016
kind: plan
title: Read-only issue-analysis fixture template
status: complete
updated: 2026-10-11
related: [SPEC-0014]
---

# Read-only issue-analysis fixture template

## Objective and dependencies

Implement the independently tested saved-fixture agent slice in [SPEC-0014](../specs/SPEC-0014-issue-analysis-template.md). Root owns shared SDK pins/lock/install, publication/current/handoff and cross-component review. This agent owns only issue-analysis contracts/factory, isolated tests/evals and these records. OpenShell transfer admission, live provider compatibility and durable agent integration remain independent/unqualified dependencies; no blocked live gate is bypassed.

## Steps

- [x] Verify unused SPEC-0014/PLAN-0016, repository state/contracts, Context7 discovery, primary release metadata and native Temporal compatibility; coordinate exact pins with root before installation.
- [x] Add immutable bounded fixture contracts, one confined source-read tool and one native instrumented agent factory/output validator; no shared ports or durable wrapper.
- [x] Add saved development fixtures and evaluator-only scripted oracles, native TestModel/FunctionModel/override positive and negative checks, UsageLimits and local native Evals span/repeat checks.
- [x] Run isolated checks/report, retain failed attempts, freeze component inputs, review against Corsair review skill and record finite coverage/limits. Root performs broader checks, CURRENT update and handoff/publication.

## Validation and progress

Private evidence: `.runs/parallel-foundations-20261011/pydantic-agent/`. Primary PyPI/release JSON and immutable upstream source files remain there. Historical `source-v1.json` retains nine earlier input hashes (it has no separate byte-copy snapshot). Current `source-v2.json` and `source-v2/` retain all eleven actual inputs, including shared pyproject/lock pins, component code/tests/eval/oracles and three fixtures. Manifest SHA256:`61c0ab763ff817e9de6fa3cd8e579a43d84da721ec0c0a9c630a837df7c55ff6`. Later edits require a new snapshot rather than changing either historical manifest. `attempts.json` and the subsequent `attempts-v2.json` record these attempts:

| Attempt | Actual result |
| --- | --- |
| Public metadata first restricted-host read | DNS errno−3; authorized escalated public metadata/source reads then succeeded. No provider/credential reads. |
| tests-001 | 9 failed / 12 passed: stale `Agent.instrument` constructor and Dataset name assumptions. Corrected to actual capability/name API. |
| tests-002 | Interrupted exit 130; synchronous executor callbacks stalled without a test result. Separate native faulthandler diagnostic exit 1 after 10s showed main asyncio selector/idle AnyIO worker; cause unconfirmed. No success claim. Cheap callbacks/tools/validators now async. |
| Diagnostic import | `Instrument` import failed; actual native capability is `Instrumentation`. |
| tests-003 | 3 failed / 18 passed: result usage is a property. Corrected. |
| tests-004 | 21 passed / 0 failed in 0.31s; native run_sync event-loop deprecation warning retained. |
| tests-005 | 24 passed / 0 failed in 0.33s; same native warning. Covers new missing-span negative, explicit-model refusal and native token limit. |
| Independent review | Actual native prior-run read history was accepted as current citation evidence; fixed by current native run-ID filter. No live claim attached to that earlier candidate. |
| tests-006 | 26 passed / 0 failed in 0.35s; same native warning. Actual cross-run-history refusal and preexisting-report/no-evaluation/no-overwrite regressions pass. |
| evaluation-001 | Six completed scripted cases, initial four assertions/case; successful native JSON serialization. |
| evaluation-002 | Six attempted/completed; 30/30 assertions; zero task/evaluator failures; six case trace IDs. Source/oracle equality and repeat agreement hold. |
| evaluation-003 | Final source-v2 candidate: six attempted/completed; 30/30 assertions; zero task/evaluator failures; six case trace IDs. Same exact source/oracle outputs as evaluation 002 after provenance/report fixes. |

Commands, from repository root (explicit repository cache/import paths; shared install is already root-owned):

```sh
PYTHONPATH="$PWD/src:$PWD" UV_CACHE_DIR="$PWD/.cache/uv" \
  .venv/bin/python -m pytest tests/agents/test_issue_analysis.py -q
PYTHONPATH="$PWD/src:$PWD" UV_CACHE_DIR="$PWD/.cache/uv" \
  .venv/bin/python -m evals.issue_analysis.evaluate \
  --report .runs/parallel-foundations-20261011/pydantic-agent/evaluation-new-attempt.json
```

Final evaluation 003 observes ten native model responses, four successful source reads, estimated 984 input/528 output tokens and summed case task duration 0.056071858s (single direct fixture process, concurrency 1, two repeats). The initial evaluation 002 duration 0.055781985s remains historical. No model output correction occurred in the successful scripted cases; native request counts plus known two-response/one-response scripts expose that trajectory. Pydantic Evals omits incremented zero metrics, so the explicit native `observed_native_tool_calls` attribute records the zero-read missing-source cases. Native costs, actual provider tokens, provider transport attempts, external model revisions and production resource usage are unavailable/not applicable, never inferred as zero.

Review: the component uses native loops/validation/overrides/limits/capture/reports; domain schemas have no SDK objects; source keys cannot access a host filesystem; injection text cannot create tools; exact quotations/current-run read evidence and scope are deterministic gates. Independent reviewer re-ran the historical-read reproduction after correction and confirmed native refusal. The script refuses existing destinations before evaluation, writes reports exclusively and checks report errors/assertion failures before returning a success exit. Remaining limits include semantic reasoning, real provider authentication/error/usage paths, held-out cases, arbitrary source acquisition, OpenShell and Temporal integration. The SDK's native run_sync loop warning is retained and does not affect async evaluation.

Broader checks, current index, handoff and publication are root-owned. Root subsequently reported `make test-config`: 182 passed in 5.03s with the retained native run_sync warning, and independently audited all eleven current source hashes plus evaluation 003 raw metrics. This sub-agent did not run/edit those shared operations. No installation, Git commit/push or PR was performed by this component owner.

## Decisions and next action

The initial contract deliberately uses saved synthetic file contents rather than a host reader, source adapter, artifact framework or new execution abstraction. Fixtures qualify contract plumbing, not real security analysis. Output citations are syntactically/source grounded; each hypothesis field still requires live/evaluator semantic assessment later.

Next: root review this code/frozen report, run affected shared/offline checks and record publication. Thereafter independently admit a real configured provider or native Temporal use of this same factory/contracts, with separate configuration/evidence. Stop before OpenShell/provider/full-graph integration until those actual gates pass. Keep the existing two native issue-validation-test requirement unchanged.
