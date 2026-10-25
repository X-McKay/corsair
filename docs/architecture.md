# Directory mapping and responsibility boundaries

This implementation follows the user's linked reference architecture. A `.py` suffix is the Python equivalent of the reference's factory, dependencies, types and settings entries. Agent metadata uses JSON rather than YAML so it needs no additional parser; its schema references canonical Pydantic contracts rather than copying field definitions.

| Reference responsibility | Implementation | Owner |
| --- | --- | --- |
| Agent spec/factory/instructions | `src/corsair/agents/{producer,auditor}` | Corresponding role maintainer |
| Agent private executable tools | `agents/producer/tools.py` | Producer maintainer |
| Typed input/output/dependencies | `contracts.py`; role factory and episode input references | Corsair maintainer |
| Shared security capabilities | `tools/security/{sources,sandbox,driver,evidence}.py` | Corsair maintainer |
| Deterministic workflows | `workflows/{investigation,evaluation}.py` | Corsair maintainer |
| Durable I/O steps | `steps/activities.py` | Corsair maintainer |
| Runtime and startup identity | `runtime/{models,agent_runner,manifest,worker,artifacts}.py` | Corsair maintainer |
| Pure final policy | `policy/verdicts.py` | Corsair maintainer |
| CLI observability/domain scorer | `cli.py`, `observability/evaluation.py` | Corsair maintainer |
| Datasets/evaluators/experiments/fixtures/baselines | Named subdirectories under `evals` | Evaluation maintainer |
| Unit/native/workflow/replay/security tests | Named subdirectories under `tests` | Changed component owner |
| Risk, threat and operation docs | Named subdirectories under `docs` | Corsair maintainer |
| Trusted image and operator configuration | `deploy/python`, `deploy/settings.example.json` | Corsair operator |

There are no runtime skills yet: the two role prompts are enough for the initial recipe. There is no empty `skills` catalog or duplicated development/runtime skill set. If private skills are later needed, package them next to the consuming agent; only move them to `src/corsair/skills` after an actual shared need. Coding-agent instructions are currently `AGENTS.md`; any future reusable coding skills belong in `.agents/skills`.

## Native responsibilities

ADK provides the agent/tool schema, Runner, callbacks, session service and model connectors. Temporal provides replay, workflow/task scheduling, cancellation, activity execution and bounded child coordination. Docker's SDK provides native lifecycle, isolation configuration and immutable container identity. Pydantic supplies the single wire schema. Pytest and coverage are the first recipe's native observer.

Corsair retains only domain functionality that SDKs cannot decide: source admission, recipe restrictions, immutable evidence binding/reconciliation, the scoped verdict table, and scoring with human-owned oracles. There is no custom provider protocol, agent graph, generic backend registry, skill engine or scheduler.

## Operator interface boundary

The CLI is an operator/view layer over these native components, not another execution engine. A live inspection obtains phase/round or batch completion from Temporal workflow queries and a watch waits for the SDK workflow result; it does not synthesize progress from elapsed time, model calls, or activity heartbeats. The worker uses the Temporal SDK worker lifecycle, and client connection uses the configured SDK client/namespace rather than a custom connection retry broker.

`doctor` asks the configured Docker and Temporal services about the actual operator dependencies (daemon/image/runtime, settings paths, namespace, and task-queue pollers). It does not call a model, validate credentials, start infrastructure, or convert preflight into a security conclusion. Human rendering is a compact presentation of a committed/native result; JSON remains the machine-result stream. Logs are a sanitized metadata channel, not an evidence, prompt, source, payload, or reasoning transport. The detailed intended CLI contract and its validation gate are in [PLAN-0106](development/plans/PLAN-0106-cli-audit.md).

## Durability

An investigation activity episode may be lost before completion; it is not promised to resume at a specific model call. Activities with side effects default to one attempt. Before native execution, the local store publishes an immutable operation intent. A committed observation is reconciled by its identity; an intent without a committed observation is uncertain, even when no container remains, and is not replayed automatically. This intentionally favors honest uncertainty over duplicate execution.

Final recording is idempotent and retried through Temporal. Workers and clients share the artifact root. An artifact-host loss is not recoverable without backups/shared storage. Planned team/AWS scale changes are not prematurely implemented in this pilot.
