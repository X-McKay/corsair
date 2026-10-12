---
id: SPEC-0013
kind: spec
title: Native Temporal fixture foundation
status: accepted
updated: 2026-10-11
related: [PLAN-0015]
---

# Native Temporal fixture foundation

## Goal and scope

Implement one deterministic fixture parent/child workflow under [Milestone 3](../../implementation-plan.md), independently of OpenShell and model providers. Follow [architecture](../../architecture.md) and [recovery](../../execution-and-recovery.md): Temporal history owns state, I/O belongs in activities, and retry ownership is explicit. This first slice does not connect the investigation graph or qualify production durability, artifact storage, OpenShell operations, agent execution or tracing.

## Boundaries and design

`FixtureRequest` and its small immutable results are stdlib dataclasses without vendor objects. The explicit request carries a bounded logical operation ID, at most 4096 UTF-8 bytes, one supported fixture scenario, and an optional signal barrier. Fixture payloads are inert trusted test values; no source repository, command, provider credential or arbitrary resource path is accepted.

`FixtureInvestigation` starts one `FixtureStage` child with a stable parent-derived ID and native cancellation propagation. The child schedules two separate native activities. Pure preparation may retry at most three times within 30 seconds. A permanent refusal is a native nonretryable application error. Completion has exactly one allowed attempt: a simulated unknown delivery becomes a visible `unknown` result with its identity and attempt count, without resubmission. Native timeout/infrastructure failures retain their cause chain rather than being converted into fixture application conclusions. Workflow code performs no file/network/model/OpenShell I/O.

The signal barrier follows completed preparation and precedes completion. It admits a controlled worker replacement/cancellation observation without a real resource. Cancellation remains native Cancelled status; no success result hides it. Cleanup is `not_required` because these fixture activities allocate no external resources. This does not qualify resource cleanup or actual unknown external dispatch.

Use default native dataclass conversion, Worker, RetryPolicy, query/signal, Client history export and Replayer. No custom converter, scheduler, job ledger, deployment abstraction or retry framework is needed. Service startup remains an explicit operator operation; tests connect only to a selected owned endpoint and never download/start an implicit server.

## Acceptance and validation

- Offline native ActivityEnvironment demonstrates attempt metadata and transient/permanent/unknown error policy; boundary cases refuse invalid/unbounded input. These checks do not prove server retries or persistence.
- Actual local service tests demonstrate parent/child completion, native preparation retries, permanent refusal, single unknown completion attempt, waiting-child cancellation, and graceful fresh-worker restoration without repeating completed preparation.
- Export and replay actual parent/child histories through native Replayer. Saved histories remain private under ignored evidence directories. Workflow replay invokes no external activity.
- A persistent-service restart needs an actual owned SQLite/service process stop/restart with pending history restored; worker replacement alone cannot meet that gate.
- Record timing/JUnit, native workflow/run/event identities, observed attempts and final statuses. Model/provider/OpenShell calls are absent by construction; Temporal RPC/internal retry counts and tracing remain unmeasured unless separately collected.
- Production databases/auth/TLS, service/worker crash mid-activity, cancellation during a dispatched activity, activity timeout/lost completion, cleanup resources, artifact references/invalidation, tracing and cross-version workflow compatibility remain unqualified.

## Decisions and open questions

The user's resumed HANDOFF-0023 parallel foundation direction authorizes this bounded slice. Root owns shared dependency pins/lock, runtime assignment and publication. SPEC-0013/PLAN-0015 were verified unused before allocation.

Selected Python SDK is [temporalio 1.34.0 immutable metadata](https://github.com/temporalio/sdk-python/blob/1.34.0/pyproject.toml), which supports Python 3.12. [PydanticAI 2.55.0 immutable metadata](https://github.com/pydantic/pydantic-ai/blob/v2.55.0/pydantic_ai_slim/pyproject.toml) declares temporalio >=1.27.0. Declared dependency compatibility is distinct from a direct/durable agent check. The [stable CLI 1.9.1](https://github.com/temporalio/cli/releases/tag/v1.9.1) embeds [service 1.32.0](https://github.com/temporalio/cli/blob/v1.9.1/go.mod); newest standalone [service 1.32.1](https://github.com/temporalio/temporal/releases/tag/v1.32.1) is a separate tuple. Context7 SDK discovery indexed 1.27.0 and was used for API discovery, not authoritative release selection.

Native references: [SDK 1.34.0 usage/testing/replay](https://github.com/temporalio/sdk-python/blob/1.34.0/README.md), [ActivityEnvironment](https://python.temporal.io/temporalio.testing.ActivityEnvironment.html), [PydanticAI native integration](https://pydantic.dev/docs/ai/capabilities/durable_execution/temporal/). Future agents must use that integration rather than one opaque retryable whole-agent activity.
