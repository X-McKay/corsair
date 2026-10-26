# Architecture overview

Corsair validates a reported security finding against a pinned source snapshot. Google ADK runs two bounded, typed agent episodes: a **producer** that proposes a benign/exploit payload pair and an outcome-blind **auditor** that can only reject a proposal. A deterministic, coverage-gated **kernel** in trusted code admits the target, runs the differential pair in a sandbox, checks exact target-line coverage, and decides the label. Temporal runs each ADK episode as one ordinary activity and coordinates rounds, deadlines, cancellation, and recording. No model ever assigns a verdict.

This section explains the implemented design. Exact contracts, settings, commands, and qualification records remain in their owning source, reference, guide, and plan pages rather than being copied here. Current plans, open decisions, and archived evidence are indexed in [plans](../plans/README.md).

## Architecture map

```text
Operator configuration and worker-only credentials
                  │
CLI / typed Python API ──► Temporal service ◄── Worker
                                  │                │
                                  │                ├── producer ADK episode   (one activity)
                                  │                ├── auditor ADK episode    (one activity)
                                  │                ├── admitted immutable source snapshot
                                  │                ├── sandbox port → Docker differential runs
                                  │                ├── coverage-gated kernel (verdict in code)
                                  │                └── immutable artifact store
                                  ▼
                       durable investigation result (one of six labels)
```

The package keeps those concerns explicit:

```text
src/corsair/
  agents/          producer and auditor factories, instructions, toolsets, packaged skills
  contracts/       canonical SDK-free Pydantic models, including the payload pair and labels
  ports/           typed inference, source-snapshot, and sandbox boundaries
  adapters/        ADK, local-source, Docker, filesystem, and Temporal SDK code
  entrypoints/     CLI, typed Python API, worker, diagnostics, terminal rendering
  policies/        the deterministic kernel gates and verdict table; packaged risk assessment
  workflows/       deterministic Temporal coordination of episodes and gates
  steps/           activities, manifests, differential execution, receipt verification
  observability/   sanitized lifecycle logging
  evaluation/      isolated-agent evaluation and external scoped scoring
```

There is no application-owned agent graph, scheduler, generic provider protocol, dependency-injection container, or remote-SCM/HTTP-service placeholder. The source-control capability admits a local source tree into an immutable snapshot; the sandbox port is answered by the Docker adapter, and an OpenShell adapter is deferred rather than stubbed.

## Read by question

| Question | Page |
| --- | --- |
| What people, services, and trust boundaries surround Corsair? | [System context](system-context.md) |
| What does each package own and where do integrations stop? | [Components](components.md) |
| How do source, payloads, coverage, evidence, and labels move? | [Data flow](data-flow.md) |
| What runs together and what must persist? | [Deployment architecture](deployment.md) |
| Which protections and limits apply? | [Security architecture](security.md) |
| Why are rounds, ports, evidence, and the payload-pair verdict designed this way? | [Architecture decisions](decisions/) |

## Two agents, one kernel

- **Producer.** Read-only source tools (`read_file`, `list_files`) over the admitted snapshot plus the role-filtered skills toolset. It returns one JSON payload **pair**: a benign payload and an exploit payload for the same target seam. It never runs code, never writes a probe, and never sees an exploit outcome. See [`src/corsair/agents/producer/`](../../src/corsair/agents/producer/).
- **Auditor.** No tools, native structured output, outcome-blind. It reviews the finding, source excerpt, and proposed pair and may only **reject**; it cannot accept its way to a label. See [`src/corsair/agents/auditor/`](../../src/corsair/agents/auditor/).
- **Kernel.** Trusted code owns the recipe, writes the probe at run time from the proposed payloads, runs the differential pair, verifies coverage and receipts, and applies the verdict table. Gates run in a fixed order: `control_run` + `control_coverage`, `exploit_run` + `exploit_coverage`, `evidence_agreement`, `blind_audit`, the target-line binding and both-runs coverage gate, and an optional `fixed_differential` confirmation. (Request load already binds `finding.file` to the recipe's module; a cheap pre-model `target_binding` gate is planned follow-up.) The policy module is [`src/corsair/policies/verdicts.py`](../../src/corsair/policies/verdicts.py).

## Design invariants

- The verdict is decided by code. Models propose and review; the kernel labels. `ProducerDecision` and `AuditResult` are canonical Pydantic contracts in [`src/corsair/contracts/agents.py`](../../src/corsair/contracts/agents.py); the result labels live in [`src/corsair/contracts/results.py`](../../src/corsair/contracts/results.py). This page does not reproduce a changing schema.
- The auditor never sees an outcome. Its packet excludes execution receipts, coverage, fixtures, oracles, and prior labels.
- Control and exploit come from one differential run pair that differs only in payload. The same snapshot, recipe, image, and fixed arguments apply to both.
- **Exact target-line coverage is required in both runs before any observation counts.** A run that did not execute the finding's target line proves nothing about it; this is the primary guard against a false `EXPLOIT_NOT_DEMONSTRATED`.
- `EXPLOIT_NOT_DEMONSTRATED` requires at least two independent producer sessions (`negative_threshold = 2`) whose coverage-valid exploit runs all failed to demonstrate the condition. One miss is `INCONCLUSIVE`.
- `EXPLOIT_DEMONSTRATED` rests on the vulnerable-revision differential (healthy control, covered exploit demonstration, non-rejecting audit). A fix revision is optional confirmation: when supplied it confirms the label if the benign control still passes and the exploit no longer demonstrates, and withholds it only if the exploit still demonstrates on the fix.
- Each ADK episode is one Temporal activity with a single attempt; Corsair does not use the experimental ADK Temporal plugin ([ADR 0001](decisions/0001-sdk-owned-durable-rounds.md)). Uncertain side effects are reconciled by identity, not replayed.
- Shared artifacts are required for worker/client inspection and recovery. A local artifact host remains a single-host durability limit.

The six labels are `EXPLOIT_DEMONSTRATED`, `COMPONENT_EXPLOIT_DEMONSTRATED`, `EXPLOIT_NOT_DEMONSTRATED`, `INCONCLUSIVE`, `UNABLE_TO_RUN`, and `ERROR` ([ADR 0004](decisions/0004-payload-pair-and-coverage-gated-verdict.md)). `COMPONENT_EXPLOIT_DEMONSTRATED` is a genuine component-seam demonstration of an application-scope claim whose application reachability was not established (developer next step: harden the component or prove an upstream guard blocks the input). The costliest error is a false `EXPLOIT_NOT_DEMONSTRATED`, and every gate is ordered to make that label the hardest to reach.

The [packaged risk assessment](../../src/corsair/policies/risk.md) is the authority for risk acceptance and residual-risk language. Architecture describes the design; it does not claim production readiness, hostile-target attestation, or population-level model accuracy. Python is the running pilot runtime; JavaScript, Java, Ruby, and Perl rows exist in the corpus matrix but are not qualified runtimes.
