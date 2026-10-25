# Deployment architecture

This page describes the runtime topology and persistence dependencies. It is not an operational deployment walkthrough; use the [deployment guide](../guides/deployment.md) for environment preparation, commands, and run-time checks.

## Runtime topology

```text
Client machine/process                    Worker environment
┌─────────────────────┐                  ┌──────────────────────────────────┐
│ CLI or typed Python │── Temporal API ─►│ Temporal SDK worker               │
│ API                 │                  │  ├─ workflows and activities      │
│ offline inspect ────┼── shared path ───┼─┤ ArtifactStore                   │
└─────────────────────┘                  │  ├─ Google ADK → model provider   │
                                         │  └─ Docker SDK → Docker daemon    │
                                         └──────────────────────────────────┘
                                                  │                 │
                                          Temporal persistence   pinned image and
                                                               short-lived containers
```

The worker registers ordinary Temporal workflows and activities on one configured namespace and task queue. Client and worker may be separate processes, but every participant that must inspect or reconcile a result needs the same artifact root. The model provider is reachable from the worker only; credentials are worker-environment secrets rather than stored Corsair configuration.

The Docker daemon and reviewed image are required at the worker-side evidence boundary. Target containers are created by the Docker SDK for a single control or adversarial role and then removed with identity-based cleanup confirmation. There is intentionally no host-process evidence fallback when Docker, its image, or its receipt is unavailable.

## Persistence and recovery model

Temporal history preserves workflow coordination, timers, cancellation, and finalization state. The artifact store preserves source archives, manifests, raw receipts, evidence bundles, committed operation mappings, and final results. Both are needed for meaningful recovery:

- a completed committed operation can be reconciled from its immutable artifact mapping;
- an intent without a committed observation is uncertain and must not be blindly re-executed;
- final result recording is idempotent and has its own retry allowance;
- loss of a local artifact host makes its results unretrievable even when Temporal history survives.

A production-grade recovery promise consequently requires shared/durable artifact storage and a durable Temporal deployment. Neither is supplied merely by pointing a client at a Temporal server. Recovery procedures and restoration limits are documented in [disaster recovery](../operations/disaster-recovery.md).

## Configuration ownership

The operator owns `source_root`, artifact-root placement, Temporal address/namespace/task queue, image/runtime, resource limits, model selection, and budgets. Those values are bound into manifests where relevant. Source and target execution must run only on a dedicated disposable host appropriate to the risk of the admitted code. Docker credentials and its socket must not reach target containers.

Nix pins the development-shell tools, and `uv.lock` pins Python dependencies. This improves reproducibility but is not a fully hermetic deployment guarantee: Docker daemon/image availability, Temporal persistence, artifact storage, and model-provider behavior are external dependencies.

## Supported and qualified scope

The documented platform target is Linux amd64 and macOS arm64. Current local qualification recorded a physical-Mac run with 134 passing tests, real Docker/Temporal, and the enabled live-auditor gates. The current local Linux amd64 revision was not rerun. The isolated producer freeze is 3/3 (one diagnostic case repeated three times) and the auditor freeze is 6/6 (two cases repeated three times); the native full live model batch is 2/3 because the safe-case second round retained an execution error. That limitation remains open in [ISSUE-0010](../plans/active/ISSUE-0010-live-safe-case-probe.md).

These results qualify bounded local behavior, not production deployment, host-loss recovery, hostile-target integrity, provider portability, or population-level model accuracy. See [Security architecture](security.md) and the packaged [risk assessment](../../src/corsair/policies/risk.md) before choosing an operating environment.
