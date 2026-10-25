# ADR 0001: SDK-owned durable rounds

- **Date:** 2026-10-25
- **Status:** Accepted — implemented

## Context

Corsair needs durable investigation coordination around nondeterministic model and native-execution work. The system must enforce whole-investigation budgets, survive ordinary worker interruptions through Temporal history, preserve cancellation semantics, and avoid replaying a possible native side effect merely because delivery was uncertain.

Google ADK provides the agent runner and native callbacks. Temporal provides durable workflows and activities. The upstream [Google ADK Temporal integration](https://docs.temporal.io/develop/python/integrations/google-adk) exists, but Corsair does **not** use the upstream `GoogleAdkPlugin` integration.

## Decision

Temporal owns the workflow, bounded rounds, root budgets, deadlines, cancellation, and final result recording. Each producer or auditor activity creates one fresh, ordinary ADK `Runner.run_async` episode. ADK owns its native agent execution, structured output, and callbacks; Temporal activities own the episode boundary and other nondeterministic work.

Model and native-side-effect activities use a single attempt. Before native evidence execution, trusted code publishes an immutable operation intent. A completed observation may be reconciled by identity; an intent without a committed observation is uncertain and is not automatically rerun. Final result recording is separate, idempotent, and retryable.

## Alternatives considered

1. **Use Temporal’s upstream GoogleAdkPlugin integration.** It could offer a different ADK/Temporal integration model, but it is not the implemented design and would change the persistence, testing, and failure boundary. Corsair instead uses ordinary activities around fresh SDK-owned episodes.
2. **Let ADK own the durable agent loop.** This would blur whole-investigation budgets, native evidence reconciliation, and Temporal’s deterministic workflow boundary.
3. **Build an application scheduler or agent graph.** That would duplicate established SDK responsibilities without a demonstrated capability gap.
4. **Retry all interrupted activities.** This can repeat a model request or a possible container side effect and falsely turn unknown delivery into a successful retry.

## Consequences

The durable unit is an investigation round/activity, not an individual model call or ADK turn. An episode lost before its activity completes is not promised to resume at the same model call; the result can carry incomplete usage or an operational status. This is a deliberate limit, not an unnoticed reliability gap.

The choice keeps workflow code deterministic and makes side-effect ownership explicit. It also means that adopting the upstream plugin later would require a separate architecture decision, conformance review, and qualification; its availability does not authorize a substitution. See [Data flow](../data-flow.md) and [ADR 0003](0003-immutable-native-evidence.md) for the corresponding reconciliation design.
