# Progressive implementation plan

Build and qualify one boundary at a time. Each milestone produces executable checks, an attributable result, and retained evidence before subsequent components depend on it. SDK reuse and isolated local evaluation apply from the first component.

## Milestone 0 Design contracts

Walk a reviewed Java vulnerable/fixed path-traversal pair through the investigation contract, graph, artifact ownership, and verdict gates. Confirm that the same two tests can exercise both revisions and identify where application behavior differs from sandbox enforcement. Specify exact schema fields when implementation begins; retain the meaning established in this bundle.

Deliverables are an example input, environment recipe, two-test specification, expected per-revision results, diagnostic examples, and example report. They can be manually supplied fixtures. No model or cluster is required for this walkthrough.

## Milestone 1 OpenShell in kind

Status: bounded native 1A–1F qualified on the selected single-node Linux amd64 tuple; [the closure report](qualification/openshell-recovery.md) records the two final recovery matrices, failures and immutable cleanup. Startup-latency [ISSUE-0004](development/issues/ISSUE-0004-native-admission-readiness.md) is resolved as a bounded measured observation; exceeding the original local 120-second wait is not proof of an upstream defect. Future sandbox-readiness calls use the pinned API default 300s; a separate [six-sample native baseline](qualification/openshell-readiness.md) passed with full cleanup. The complete corrected 1F interruption matrix is not rerun. Historical qualification retains its original source/budget. Production reliability and subsequent milestones remain unqualified; each fresh runtime must pass its mandatory native gates.

The [detailed OpenShell milestone](openshell-milestone.md) specifies the proposed files, topology, progressive test slices, native SDK/CLI paths, evidence, and handoff to the application adapter.

Pin kind, Kubernetes, Agent Sandbox, OpenShell, image digests, and node/kernel assumptions. Provision the supported local topology and use native CLI/SDK commands to verify readiness, permitted scratch access, forbidden filesystem access, approved/denied network access, limits, transfer, and confirmed deletion. Use a network-denial test that distinguishes policy enforcement from an unavailable endpoint.

Acceptance: the real boundary works on the selected tuple; each required negative check has independent evidence; failed setup names the failing layer; cleanup is confirmed. Test known-good Java and Python toolchains separately from repository setup. Production namespace deployment declares the corresponding cluster prerequisites.

Deliver a minimal repeatable setup and qualification command, evidence report, versions, and runbook. Do not patch the gateway or add an inspector unless a demonstrated mandatory check cannot be achieved through supported interfaces; record the SDK gap first.

## Milestone 2 Sandbox and artifact adapters

Status: the first [create/readiness/delete and host receipt slice](qualification/openshell-adapter-lifecycle.md) is qualified on two fresh admitted nodes. The full milestone is incomplete; execution/transfers/output/failure contracts, immutable artifact storage and worker-loss cases remain. Native deletion lacks an atomic expected-ID condition, so the current slice requires an operator-exclusive workspace and nonreused names.

Implement only the required port methods using SDKs/standard storage operations. Exercise create, transfers, exec, event collection, destroy, output bounds, timeout, interrupted transport, and unknown delivery. Capture immutable source snapshots without running hooks; validate file types, path confinement, and digest identity.

Acceptance: real adapter contract tests pass, completed/unknown commands are distinguishable, artifacts survive worker restart, and untrusted workloads cannot alter authoritative records. Fixture adapters are explicit alternatives for tests.

## Milestone 3 Temporal foundation

Provision persistent local Temporal, then use deterministic fixture stages to demonstrate parent/child workflow execution, activity failure, restart, cancellation, replay compatibility, and supported tracing. No live model is needed.

Acceptance: progress and artifacts remain consistent after interruption; unknown side effects are not blindly repeated; cleanup outcomes remain visible; workflow history is the job state authority. Local development configuration is clearly separate from production service configuration.

## Milestone 4 Deterministic two-test validation

Run manually supplied environment recipes, plans, and test patches through fresh setup and verification sandboxes. Produce Markdown/JSON reports with scope, two test outcomes, failure records, performance, and cleanup status. Add reviewed vulnerable/fixed Python and Java pairs.

Acceptance: controls pass both revisions; security assertions distinguish the pair; wrong assertions, skipped tests, changed source, stale results, sandbox interference, dependency failures, and unknown execution cannot verify a fix. A saved case can rerun without an agent.

## Milestone 5 Model adapters and agent template

Use native PydanticAI local endpoint and Bedrock integrations. Establish TestModel/FunctionModel, native overrides, instrumented factory, output schema, tool authority, usage limits, and one isolated evaluation entry point.

Acceptance: provider authentication/errors and unavailable usage are visible; direct and Temporal execution use the same agent; each execution backend is explicit; native traces and evaluation reports work locally without a hosted telemetry account. Actual supported provider calls qualify provider compatibility; mocks qualify only contracts.

## Milestone 6 Individual agents

Add agents in order: issue analysis, environment, test planning, test authoring, evidence assessment. Each consumes saved predecessor artifacts. Build its reviewed development/held-out cases, trajectory checks, repeat comparisons, robustness tests, and performance baseline before connecting it to the graph.

Acceptance: each agent is independently runnable, has one objective and restricted authority, passes its mandatory negative cases, and supplies a measured quality/efficiency baseline. Prompt edits need no upstream rerun when frozen inputs remain valid.

## Milestone 7 Complete graph and issue sources

Connect the qualified stages. Add GitHub issue capture and Azure DevOps work-item capture as independent adapters, preserving the same finding contract. Start with fixture inputs when credentials are unavailable; do not call that live-provider qualification.

Acceptance: the complete workflow handles reproduced, refuted-in-scope, not-reproduced, unsupported, blocked, failed, and unknown cases. Reports link to the underlying frozen evidence. Version changes follow explicit invalidation; there is no silent provider/backend fallback.

## Milestone 8 Existing cluster and bounded scale

Use the same chart with production values for identity, registries, storage, resource limits, Temporal endpoint, retention, and telemetry. Qualify platform prerequisites and production authentication. Increase independent-investigation concurrency incrementally, retaining one graph per investigation.

Acceptance: no cross-investigation data/credential leakage; durable artifacts and lifecycle recovery work across workers; admission limits, provider throttling, queue time, cancellation, and orphan cleanup are measured. Qualify production storage concurrency semantics before multiple workers share it.

## Operator entry points

The planned CLI is thin glue over existing functions and SDK commands. Illustrative entry points are `doctor sandbox`, `doctor model`, `capture-source`, `agent run`, `agent eval`, `verify --case`, and `investigate --input`. Every command records mode and configuration identity.

Use pytest and native SDK test facilities for checks and Pydantic Evals for datasets/reports. Reuse these commands in CI. Avoid separate local and production implementation paths, custom dashboards, homegrown deployment systems, or broad automatic repair loops.

## Deferred scope

Repository-supplied environment hint files, automatic remediation/issue closure, arbitrary image generation, deployment-scope findings, online judge interventions, new sandbox providers, and additional agents are outside the initial release. Admit them only with a concrete case, clear owner, and measured need. The [analyst pilot](analyst-pilot-plan.md) is separately planned after technical qualification.
