# System context

Corsair accepts an operator-defined investigation request for a fixed Python callable recipe and an authorized local source tree. It returns an attributable, scoped investigation result with immutable artifacts. The system is deliberately narrow: it does not fetch repositories, expose an HTTP API, generate arbitrary probes, publish findings, or decide organizational risk acceptance.

## Actors and systems

```text
Operator
  ├── supplies reviewed settings, a bounded request, and the local source root
  ├── starts clients and workers; retains responsibility for host and risk decisions
  │
  ▼
CLI / typed Python API ── submits, observes, or cancels ──► Temporal service
                                                             │
                                                             ▼
                                                       Corsair worker
                                        ┌────────────────────┼─────────────────────┐
                                        ▼                    ▼                     ▼
                              Google ADK episode    local immutable store    Docker daemon/image
                                        │                    ▲                     │
                                        ▼                    │                     ▼
                              configured model      shared artifacts       trusted native observer
                              provider endpoint     and manifests          and target containers
```

**Operator.** The operator owns source scope, budgets, image/runtime selection, Temporal address/namespace/task queue, and deployment environment. Provider credentials are available only in the worker environment; they do not belong in requests, settings files, source snapshots, workflow arguments, artifacts, or example commands.

**Clients and Temporal.** The CLI and typed Python API submit the same native Temporal workflows. They are clients, not an HTTP service or a second orchestration layer. Temporal retains workflow history and schedules ordinary activities; its service does not replace the artifact store.

**Worker.** One standard Temporal SDK worker registers the investigation/evaluation workflows and their activities. It constructs the concrete ADK, source-snapshot, Docker, and filesystem integrations. It is the component that can reach the configured model provider and local Docker daemon.

**Google ADK and model provider.** A producer episode creates a structured `Submission`; a fresh, tool-free auditor episode creates an `AuditResult`. Both use canonical Pydantic schemas through ADK `output_schema` and native callbacks for model/tool/output limits and usage. The model provider is untrusted for verdicts and is not a persistence boundary.

**Source admission and artifacts.** The local source adapter admits only a bounded, descriptor-checked source tree under the configured root, creates deterministic archive bytes, and later exposes snapshot reads. No live checkout path is given to an agent or container. The local artifact store content-addresses blobs and immutably maps operation identities to committed artifacts.

**Docker observer.** The worker uses the Docker SDK to create fresh restricted containers for control and adversarial roles. The container runs the packaged trusted driver against a read-only snapshot and fixtures. Docker is an important containment boundary but not proof against a hostile daemon, kernel, or arbitrary malicious interpreter.

## Information boundaries

The producer receives a public recipe configuration, admitted source excerpt, round context, and limited source-reading tools. It does not receive private fixtures, execution outcomes, verifier oracles, source paths outside the snapshot, or an execution/write capability. The auditor is separately fresh and outcome-blind; it receives the finding, public recipe configuration, source excerpt, and submission, with no tools.

The native observer creates private fixture material only at execution time. It keeps that material out of agent prompts, submission data, logs, evidence reasons, and driver job data. Logs are sanitized operational metadata, not an alternate source or evidence channel.

## Current integration boundary

Implemented integrations are local source snapshots, filesystem artifacts, Docker SDK execution, native Google ADK model paths (including configured LiteLLM-compatible routes), and the Temporal Python SDK. Remote SCM, Bedrock-specific inference, generic vendor wrappers, and an HTTP API are not implemented placeholders. A future integration must supply a real authorized capability at the existing port and be qualified independently; a module name alone is not an integration.

For package-level ownership, see [Components](components.md). For the sequence of a single investigation, see [Data flow](data-flow.md). Security limits and operating constraints are covered by [Security architecture](security.md) and the authoritative [risk assessment](../../src/corsair/policies/risk.md).
