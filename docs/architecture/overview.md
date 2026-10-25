# Architecture overview

Corsair is a personal-use security-investigation pilot for one bounded Python secret-disclosure recipe. Google ADK runs the producer and auditor as bounded, typed agent episodes. Temporal coordinates the investigation’s durable rounds, deadlines, cancellation, and final recording. Trusted code—not either model—admits source, executes the native observer, validates evidence, and assigns the scoped result.

This section explains the current implementation. Exact contracts, settings, commands, and historical qualification records remain in their owning source, reference, guide, and plan pages rather than being copied here. Current plans, open issues, and archived evidence are indexed in [plans](../plans/README.md).

## Architecture map

```text
Operator configuration and worker-only credentials
                  │
CLI / typed Python API ──► Temporal service ◄── Worker
                                  │                │
                                  │                ├── ADK producer/auditor episodes
                                  │                ├── admitted local source snapshots
                                  │                ├── Docker-native trusted observer
                                  │                └── immutable artifact store
                                  ▼
                       durable investigation result
```

The package keeps those concerns explicit:

```text
src/corsair/
  agents/          role factories, prompts, metadata, and producer tools
  contracts/       canonical SDK-free Pydantic models
  ports/           typed inference, source-snapshot, and sandbox boundaries
  adapters/        ADK, local-source, Docker, filesystem, and Temporal SDK code
  entrypoints/     CLI, typed Python API, worker, diagnostics, terminal rendering
  policies/        pure disposition/fix decisions and the packaged risk assessment
  workflows/       deterministic Temporal coordination
  steps/           activities, manifests, evidence orchestration, verification
  observability/   sanitized lifecycle logging
  evaluation/      isolated-agent evaluation and scoped scoring
```

There is no application-owned agent graph, scheduler, generic provider protocol, dependency-injection container, or remote-SCM/Bedrock/HTTP-service placeholder. The current source-control capability admits a local source tree into an immutable snapshot; it is not a remote checkout implementation.

## Read by question

| Question | Page |
| --- | --- |
| What people, services, and trust boundaries surround Corsair? | [System context](system-context.md) |
| What does each package own and where do integrations stop? | [Components](components.md) |
| How do source, model output, evidence, and results move? | [Data flow](data-flow.md) |
| What runs together and what must persist? | [Deployment architecture](deployment.md) |
| Which protections and limits apply? | [Security architecture](security.md) |
| Why are durable rounds, typed ports, and immutable evidence designed this way? | [Architecture decisions](decisions/) |

## Design invariants

- `Submission` (including `PlanRevision`) and `AuditResult` are canonical Pydantic contracts in [`src/corsair/contracts/agents.py`](../../src/corsair/contracts/agents.py). ADK consumes those models through native `output_schema`; this page does not reproduce a changing schema.
- The producer can only use `read_file` and `list_files` against an already admitted immutable snapshot. It proposes JSON payload data, never executable probes or assertions. The tool-free auditor receives an outcome-blind review packet.
- Native Docker execution returns raw immutable receipts, not a verdict. Verification checks the receipt, source/submission identity, container cleanup, driver report, and relevant coverage before policy code considers a disposition.
- Temporal durability is at the round/activity level. A fresh ADK episode is not resumable at an arbitrary model call; uncertain side effects are reconciled by identity and are not automatically replayed.
- Shared artifacts are required for worker/client inspection and recovery. A local artifact host remains a single-host durability limit; Temporal history alone cannot recreate lost artifacts.

The [packaged risk assessment](../../src/corsair/policies/risk.md) is the authority for risk acceptance and residual-risk language. Architecture describes the design; it does not claim production readiness, hostile-target attestation, population-level model accuracy, or application-level exposure from component evidence alone.
