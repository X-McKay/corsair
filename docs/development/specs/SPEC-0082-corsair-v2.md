---
id: SPEC-0082
kind: spec
title: Corsair v2 native agent platform
status: accepted
updated: 2026-10-14
related: [PLAN-0097, SPEC-0081, ISSUE-0009]
---

# Corsair v2 native agent platform

## Goal and scope

Implement the user-approved Corsair v2 redesign as a Python CLI platform, with no website or web console. Push only to the requested `manus-test` branch. The user additionally requires thorough official PydanticAI/Harness, Temporal, OpenShell, and evaluation documentation research; native capabilities before custom infrastructure; no shipped placeholders or stubbed functionality; and real-model end-to-end validation, optionally with a small Qwen model through Ollama or llama.cpp.

The design reference is the Corsair v2 specification supplied in this task. The new implementation is isolated under `src/corsair/v2/`; legacy modules remain available for compatibility and historical evidence, but do not supply a silent fallback. The v2 CLI is explicit. The redesign supersedes the old fixed-six-role topology for v2 only, while retaining independent control/exploit author contexts, a frozen outcome-blind validity review, and deterministic scoped dispositions.

## Boundaries and design

Use native PydanticAI agent manifests, Harness capabilities, UsageLimits, structured outputs, model providers, instrumentation, and TemporalDurability. One Temporal parent workflow owns lifecycle; native model/tool activities preserve fine-grained durability. OpenShell native SDK/CLI operations supply actual sandbox lifecycle, execution, and transfer. Do not substitute host execution for untrusted workload execution. SQLite stores append-only receipts and derived query state; retained immutable bytes reuse the existing tested LocalArtifacts primitive. Source, profile, agent/skill/tool, dataset, evaluator, and executed probe identities are recorded.

The agent proposes and gathers evidence; deterministic gates own the final disposition. Exactly two native probes are independently authored: ordinary benign control and adversarial security regression through the real source seam. Review their frozen source/plan/bytes before execution, without outcomes. Absent or failed control, discovery failure, unknown command delivery, policy denial, invalid source linkage, an unqualified backend, or missing evidence cannot prove a repair or broad absence of a flaw. Missing optional witness telemetry is not itself a blocker; report trust and scope accurately. Generated probes never execute in the trusted worker.

Use Pydantic Evals as the evaluation engine, not a new evaluation scheduler. Support actual dataset import, frozen manifests, source-only agent evaluations, full run evaluations, explicit repeats, local traces/trajectory checks, persisted reports, and compatible baseline comparisons. Agent-visible inputs never include benchmark expected labels. Report tokens, latency, request/tool counts, errors, accuracy, coverage, abstention, false confirmation/missed confirmation, trajectory checks, and per-language/framework/CWE/agent/model strata; missing telemetry is unknown, not zero. Keep first-attempt and final outcomes attributable. Public benchmark licenses and provenance remain explicit; imported source-only tasks are not called execution benchmarks.

## Acceptance and validation

Ship working commands for configuration/doctor, investigation, durable worker/submit/status/cancel, evidence/artifacts/diffs/replay/reconciliation, benchmark import/evaluation/report/comparison, and native schema export. Validate immutable capture/storage and idempotency; real native agent/Harness tool calls; actual bounded sandbox commands; real Temporal activity execution and replay; cancellation/uncertain effects; deterministic verdict refusal cases; per-language evaluation and denominator integrity; secret/label separation; wheel asset completeness; and existing offline compatibility checks.

Real Qwen inference and actual Temporal/OpenShell execution are separate observed gates. If native runtime prerequisites fail, retain the failure and report that boundary unqualified rather than return fabricated results or register an unfinished substitute. Continue implementing fully functional paths that do not depend on the blocked gate. No universal CWE/language/security/reliability guarantee follows from smoke results.

## Decisions and open questions

User authorization on 2026-10-14 explicitly supersedes earlier deferred live validation for the new v2 scope. Library research and locked-version operational checks determine concrete native imports and unavoidable adapter seams. The current sandbox admits user namespaces and a real Docker container; OpenShell-specific policy/kernel/gateway admission is still to be demonstrated. The supplied v2 design is not itself runtime qualification. Implementation and actual results are tracked in PLAN-0097.

### Implementation-grounded native decisions and qualification limits

The implemented architecture uses PydanticAI `Agent`/`AgentSpec`/`Agent.from_spec`, structured Pydantic results, native `UsageLimits`, and selective Pydantic AI Harness `Skills`, bounded read-only `FileSystem`, `Planning`, `ToolOutputLimits` and `ClearToolResults`. `Planning` uses native `SqlitePlanStore` with run/stage scope. The single `CorsairRunWorkflow` (`PydanticAIWorkflow`) delegates fine-grained model/tool/workspace calls to `TemporalDurability`; it does not hide an entire agent trajectory in one opaque activity. Temporal task queues are suffixed by the full execution identity, with one immutable config/build identity per worker/replay process. `temporal_api_key_env` names an environment variable and requires TLS; secrets are not config values.

The v2 evidence topology is local POSIX content-addressed immutable artifacts plus SQLite WAL (`BEGIN IMMEDIATE`) for events, operation intents and derived state. It is process-safe within one host/storage domain, but **not** a PostgreSQL/S3/shared multi-host database or a transparent distributed artifact/path service. Multi-host storage is a separately scoped backend extension, not implemented.

The OpenShell adapter is the only v2 workload path, with aligned SDK/CLI 0.1.3 and no host/Docker fallback. The selected local Docker profile is intentionally **unqualified**. A qualification file is a locally checked operator attestation bound to SDK/CLI/profile/image/base/effective-policy/runtime fields; it is not an independently issued or cryptographically signed runtime proof. OpenShell delete is name-based without an atomic expected-UUID conditional operation, so exclusive controller ownership of the sandbox namespace is required; gateway deletion acknowledgement is not independent driver-GC proof. Production use requires qualification on the actual target host/profile.

Operator and architecture documentation is in [docs/v2](../../v2/README.md); native decisions are recorded in [newupstream-decisions.md](../../v2/newupstream-decisions.md). Parent-owned actual live outcomes will be written to [validation.md](../../v2/validation.md) after frozen-policy tests. This spec update and the documentation worker assert no new live test counts or results.
