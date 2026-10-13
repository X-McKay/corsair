# Architecture and component boundaries

The system uses a fixed graph of five PydanticAI agents plus deterministic nodes. Temporal owns durable coordination. Agents do not select their successors or allocate additional authority.

## Graph

```mermaid
flowchart TD
    A[Capture immutable issue and source] --> B[Issue identification agent]
    B --> C[Environment agent]
    C --> D[Replay setup and verify readiness]
    D --> E[Test planning agent]
    E --> F[Test authoring agent]
    F --> K[Freeze tests]
    K -->|Unit observation| L[Assessment agent: outcome-blind validity review]
    L --> G[Execute both probes fresh]
    K -->|Legacy witness observation| G
    G --> H[Assessment agent: interpret results]
    H --> I[Validate disposition and render report]
    D -->|Blocked or failed| J[Diagnostic report]
    G -->|Blocked or failed| J
```

Every node has explicit success, blocked, unsupported, failure, and unknown outcomes as applicable. Other node failures also enter finalization with their diagnostic evidence. Cleanup runs independently of report interpretation. Bounded corrections occur within an agent's stage; they do not create unrestricted graph loops.

## Agent contracts

Each agent package follows the [agent package convention](agent-packages.md): one file per responsibility, one module per model-facing tool, explicit registration.

| Agent | Objective and output | Authority |
| --- | --- | --- |
| Issue identification | Reported security concern and relevant source target, or a concrete blocker | Confined source/issue reads only |
| Environment | Successful setup recipe, dependency closure, environment evidence | Preparation sandbox commands and approved setup artifacts; no application changes or policy edits |
| Test planning | Conditional hypothesis, existing application test seam, two native unit tests by default, validity and scoped evidence requirements | Source and environment evidence reads only |
| Test authoring | Exactly two native tests, test patch, run command | Approved test writes and bounded development execution in the prepared environment |
| Evidence assessment | Pre-execution test-validity review; separate interpretation, citations, limitations and proposed disposition after execution | Frozen source/plan/patch reads for validity; result evidence and immutable review reads for disposition |

The narrowed first-stage contract is accepted in [SPEC-0024](development/specs/SPEC-0024-issue-identification.md). Its isolated factory is a replacement candidate; the existing hypothesis analyst/reviewer and single-agent Temporal workflow retain their historical contracts until separately migrated and qualified. The preserved original report is a concern to investigate, not a source-proved vulnerability.

All agents use separate contexts and receive only explicit stage inputs. No global conversation or shared mutable agent memory is required. Budgets and permissions are injected dependencies, not instructions that an agent can override.

Agent factories, output contracts, prompts, and toolsets are reused in direct and durable execution. Production graph stages use small child workflows beneath one parent investigation workflow. Native PydanticAI Temporal capabilities route model and tool operations through activities. The complete agent loop must not be wrapped in one opaque retryable activity.

## Deterministic responsibilities

Deterministic nodes acquire snapshots, resolve revisions, enforce support, replay setup, verify native discovery, freeze test artifacts, execute tests, collect receipts and policy events, validate conclusions, render reports, and manage cleanup. Their checks establish execution facts and admit explicit test-validity evidence; model prose cannot override them. Keep execution admission distinct from semantic test review. Gates consume the planned property and evidence from the real test seam; a low-level effect recorder is optional supporting evidence. Missing recorder support alone must not block a valid unit test. A passing model-authored assertion still requires source linkage and validity checks before a conclusive disposition. Unit-assertion admission consumes a separate pre-execution call of the existing evidence-assessment agent, with only source, patch, plan and reported-condition evidence available. Trusted code binds that review to the exact source and frozen observation plan/test patch; result assessment cannot create or change it. An authoring agent cannot self-attest. Missing review yields inconclusive validity, and the existing admitted witness path remains available. This is a bounded review contract, not universal automated semantic verification.

Use the same evidence contract across languages and frameworks: intended source, existing seam, benign/adversarial inputs, relevant assertions, controlled-dependency limits, discovery and fresh execution. Framework adapters translate native results; they do not add a mandatory language-specific observation mechanism. Controlled dependency doubles are permitted when they retain the real production logic that owns the tested property. Escalate to integration scope only when that property requires a real external behavior.

Environment readiness requires a relevant build and a discovered, executed baseline test or admitted native control fixture. An existing unrelated suite failure is retained and assessed; it is not silently hidden or automatically equated with environment failure.

## Ports and adapters

| Port | Contract | First implementation and extension |
| --- | --- | --- |
| Sandbox | Lifecycle, files, command results, boundary observations, cleanup | OpenShell SDK; fixture/local execution for development; another qualified backend later |
| Model selection | Supply a configured PydanticAI model and capability requirements | Per-agent named profiles: native vLLM, OpenAI-compatible Chat Completions or Bedrock Converse |
| Issue | Immutable finding and discussion snapshot | Read-only GitHub issues and Azure DevOps Services work-item REST adapters |
| Source | Resolve and acquire an exact source identity | Git acquisition without executing repository hooks |
| Artifacts | Store/read immutable objects by authorized reference and digest | Standard filesystem on persistent storage; object-storage SDK later |

Use SDK types inside adapters; keep stage contracts free of vendor SDK objects. The model boundary is a small composition/factory seam, not a new model-request protocol. Preserve backend-specific diagnostic evidence and reject unsupported required capabilities explicitly. No automatic provider or sandbox fallback is allowed.

## Deployment

The local kind deployment and existing-cluster deployment use the same application chart, images, graph, and adapters. Environment values select image registries, resource limits, storage, provider access, and external access.

Start with one worker deployment, one active investigation, a Temporal service, an OpenShell gateway, and persistent artifacts. Local Temporal may use a supported development configuration with persistent state; production uses an operator-provided qualified service and database configuration. Do not operate a second application job ledger.

Application resources are namespace-scoped. OpenShell's Agent Sandbox controller/CRDs, cluster RBAC requirements, NetworkPolicy enforcement, and node/kernel support are platform prerequisites. Local bootstrap provisions the selected prerequisites; an existing cluster's platform team supplies them. Qualification tests actual enforcement, not just resource creation. Namespace isolation does not establish isolation from a compromised node; dedicated nodes or stronger runtimes remain a platform qualification decision.

The trusted worker owns model access and sandbox lifecycle. Repository workloads have no model, issue-provider, cloud, or cluster-management credentials. Configure untrusted workload service accounts without automatic credential mounting. Restrict sandbox-to-control-plane communication according to the supported OpenShell topology.

## Organization

```text
src/corsair/
  core/                 contracts, evidence rules, verdict gates
  ports/                narrow external capability interfaces
  adapters/             SDK-backed implementations
  agents/
    issue_analysis/
    environment/
    test_planning/
    test_authoring/
    evidence_assessment/
  workflows/            Temporal graph and agent stage workflows
  composition.py        explicit adapter and agent wiring
  cli.py                thin diagnostic and evaluation entry points
evals/                  cases, reviewed labels, evaluators, baselines
tests/                  deterministic, adapter, integration, replay tests
images/                 approved toolchain images
policies/               operator-owned sandbox profiles
deploy/                 chart, kind config, environment values
docs/                   contracts, qualification evidence, runbooks
```

Each agent owns its factory, contracts, instructions, tools, and evaluation cases. Share a capability only when there is a demonstrated second consumer. Ports describe external capabilities; avoid interfaces for every internal function.

The [OpenShell milestone](openshell-milestone.md) starts with native runtime qualification under deployment, policies, images, and pytest checks. Application ports/adapters are implemented after that boundary passes; later package folders are created only when needed.

## Complexity rules

Use PydanticAI for loops, outputs, limits, providers, overrides, and instrumentation; Temporal for history, retries, timeouts, cancellation, and replay; OpenShell for sandbox mechanics; and Pydantic Evals for evaluation execution and reports.

Application-specific code is limited to stage contracts, restricted domain tools, evidence interpretation/gates, SDK translation, and composition. Do not build another scheduler, tracing system, provider protocol, credential broker, generic graph engine, or agent simulator. Additional agents, services, repair loops, or shared state require a concrete failing case, named owner, and measured benefit.

Use explicit Temporal transitions as the graph execution authority. Adding a graph library is unnecessary unless it improves implementation without duplicating durable state or scheduling.

Provider composition and current limits: [configuration runbook](runbooks/provider-configuration.md).
