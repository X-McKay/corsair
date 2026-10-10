# Execution modes artifacts and recovery

Every agent can run independently against saved inputs. Runtime and execution backend are separate selections. Production requires a qualified sandbox backend; local modes serve development and do not qualify production confinement.

## Run modes

| Runtime | Execution | Purpose |
| --- | --- | --- |
| Direct PydanticAI | Fixture or mock toolsets | Deterministic contract and behavior tests |
| Direct PydanticAI | SDK-backed local workspace | Prompt iteration on trusted fixtures |
| Direct PydanticAI | OpenShell | Live isolated agent evaluation |
| Temporal | Fixture or mock toolsets | Durability, retry, cancellation, graph tests |
| Temporal | Local workspace | Diagnose Temporal separately from OpenShell |
| Temporal | OpenShell | Full qualification and production execution |

Model selection independently chooses TestModel/FunctionModel, a local endpoint, or Bedrock. Use native agent/toolset overrides and the same agent factory. Mock models can invoke tools: deterministic tests must also select fixture toolsets and prevent unintended real provider calls. Local execution is explicit and limited to trusted fixture workspaces by default; production configuration cannot silently select it.

Read-only agents need no command executor. An execution backend is required only for stages whose tools execute code. Failure to configure a required backend is a configuration failure, not an implicit fallback.

## Artifacts and ownership

An investigation has an immutable request identity and source identities. Each stage attempt records input digests, contract version, agent/prompt version, model configuration, execution mode, image and effective policy identities, budget, and outputs. Large source archives, command output, and reports reside in artifact storage. Temporal history contains small typed state and authorized references, with native model/tool payload limits configured separately.

Artifacts are immutable once admitted. A correction creates a new attempt and explicit supersession relation. Authoritative receipts and lifecycle records are stored outside untrusted workload reach. Test/source digests are checked against expected inputs; integrity checks do not claim to prove semantic validity or detect every transient modification.

Use immutable source input and restricted test patches. Native build output and caches occupy declared writable locations or an admitted staging copy. Freeze the relevant application bytes, test patch, dependency state, and recipe before fresh verification. Rejected production-source changes cannot be laundered as generated build output.

## Invalidation

| Changed input | Required new work |
| --- | --- |
| Issue hypothesis or meaningful preconditions | Analysis and dependent environment, plan, tests, execution, assessment |
| Source commit | Capture, environment verification, plan compatibility, tests, execution, assessment |
| Toolchain, dependency state, or setup recipe | Environment verification and downstream execution; recheck plan/test assumptions |
| Test plan | Test generation, execution, assessment |
| Test bytes | Fresh execution and assessment |
| Assessment prompt | Assessment and conclusion gates over unchanged evidence |
| Sandbox policy/runtime | Requalify affected boundaries and replay affected execution |
| Shared contract | Compatibility validation for all consumers and required downstream stages |

Changing a prompt does not mutate an in-flight investigation. New versions run as new attempts or investigations. Persist provenance sufficient to reproduce comparisons; an endpoint name alone does not identify model weights. Record a served model revision when available and mark it unknown otherwise.

## Replay and retries

Workflow code owns deterministic transitions. File/network I/O and SDK calls execute in activities. Native PydanticAI integration owns durable model/tool scheduling. Replay compatibility uses SDK replayers and supported worker/workflow versioning.

Distinguish bounded model output correction, provider transport retries, Temporal activity retries, and deliberate evaluation reruns. Configure retry ownership per external operation so nested retry layers cannot amplify an unknown request. A model timeout can also leave billed usage unknown; record that uncertainty.

Commands use a stable logical operation identity. Completed native results are reconciled or reused through supported APIs. Not-dispatched operations can be attempted according to policy. An unknown dispatch is not blindly resent. Where the SDK cannot reconcile an operation safely, stop with an unknown outcome and retain diagnostics instead of implementing speculative recovery.

Fresh verification can be repeated in a newly owned sandbox as a distinct evidence attempt when explicitly requested by the workflow or operator; it does not retroactively resolve the earlier unknown dispatch. Bound both attempts and aggregate their resource use.

Use supported SDK lifecycle operations and idempotency where available. Any necessary application receipt bookkeeping must be minimal and justified by a demonstrated SDK gap, with focused failure tests.

## Cancellation and cleanup

Every sandbox carries an investigation/stage ownership identity. Prefer supported expiry, lifecycle, and cancellation features; qualify their actual behavior. Where native expiry is insufficient, use Kubernetes-supported lifecycle facilities or a minimal bounded reconciler based on the native ownership inventory. Do not maintain a second sandbox scheduler.

Record creation intent and native identity, creation outcome, deletion request, and confirmed absence where observable. Partial creation and failed cleanup remain visible. Cleanup status is `confirmed`, `unconfirmed`, or `not_required`; successful tests do not conceal abandoned resources.

The acceptance suite covers worker loss during create/exec/upload, cancellation during setup and verification, unavailable gateway, missing artifact storage, report-generation failure, and deletion failure. An operator command lists owned abandoned resources and uses the native deletion path. Artifact retention and sandbox lifetime are separate policies.

## Failure record

A typed failure records stage, responsible component, operation ID, category, evidence references, retryability, delivery state, confidence in cause attribution, and next action. Preserve the original SDK error type/cause without exposing credentials.

Categories include configuration, unsupported requirement, source acquisition, sandbox boundary, dependency resolution, registry authentication, TLS trust, toolchain/build, discovery, fixture/test infrastructure, agent contract, agent reasoning, provider, transport/unknown delivery, artifact storage, cancellation, and cleanup.

A failed security assertion is an observation, not a generic agent or infrastructure failure. A policy denial needs matching boundary evidence; missing logs or a generic network error do not prove the cause. Unknown causes remain unknown.

## Logging and measurement

Use PydanticAI OpenTelemetry spans, supported Temporal telemetry, native OpenShell events, and structured application lifecycle logs. Correlate investigation, stage, agent version, workflow/activity attempt, operation, sandbox, and artifact identities. Correlation IDs belong in logs/traces; do not use high-cardinality run IDs as metrics labels.

Measure wall time, model time, tool time, sandbox setup, queue delay, retry backoff, request attempts, executed tool attempts, tokens, and cancellations. Count failed attempts and distinguish workflow replay from actual execution. Aggregate provider usage once from leaf request evidence; do not sum both parent and child token totals. Missing usage is unavailable, not zero. Cost is an estimate with its pricing basis; local resource cost is separate from token counts.

General telemetry excludes secrets and defaults to excluding prompts/source content. Authorized diagnostic artifacts retain necessary source/test/output detail under access and retention controls. Telemetry loss and missing evaluation spans are recorded as coverage gaps, not evidence of successful behavior.
