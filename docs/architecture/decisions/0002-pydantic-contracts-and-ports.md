# ADR 0002: Canonical Pydantic contracts and narrow ports

- **Date:** 2026-10-25
- **Status:** Accepted — implemented

## Context

Corsair needs the same domain values to move through ADK episodes, Temporal activities, source admission, native evidence, evaluation, the CLI, and the typed Python API. Carrying SDK objects or loosely typed dictionaries across those boundaries would couple the domain to vendors, invite schema drift, and make isolated evaluation less meaningful.

The implementation also needs real extension seams without speculative modules for every provider or forge.

## Decision

`src/corsair/contracts/` is the canonical, SDK-free Pydantic contract package. The producer uses `Submission`, including `PlanRevision`, and the auditor uses `AuditResult` directly as native ADK `output_schema` values. Canonical validation, dynamic round/parent checks, and trusted evidence gates remain after generation. Documentation links to these models rather than maintaining a second field-by-field schema authority.

`ports/` defines only the three implemented domain boundaries: typed producer/auditor inference, admitted source snapshots, and sandbox role execution returning an artifact reference. Ports import contracts and standard-library types, never ADK, Docker, Temporal, or a concrete adapter. The ordinary worker composes the implemented adapters: native ADK/Gemini/LiteLLM paths, local source snapshots, Docker SDK execution, filesystem artifacts, and Temporal client support.

## Alternatives considered

1. **Expose ADK, Docker, or Temporal types in domain contracts.** This would make workflow, evaluation, and policy code depend on concrete SDK lifecycles.
2. **Use untyped generic role/payload or provider invocation APIs.** This hides the actual supported operations and pushes validation failures to runtime.
3. **Maintain hand-written duplicate output schemas or repair generated strings.** This would drift from the canonical model and bypass native structured output.
4. **Add placeholder remote-SCM, provider, or HTTP modules.** Empty adapters do not create a usable authorized capability and misrepresent implementation status.
5. **Keep retired import shims.** Compatibility paths would obscure the new ownership boundaries without an authorized migration requirement.

## Consequences

The contracts can be validated and evaluated without loading execution adapters, and concrete adapters can evolve behind explicit typed operations. The producer remains a data proposer with two immutable-source read tools; it is not given a generic tool/execution surface. Model capability differences still matter: native ADK handles schema/tool behavior, while Corsair retains its budget and contract checks.

Adding a source provider or vendor-specific path now requires a real adapter that fulfills an existing or justified new port, plus isolated and composed qualification. It is not satisfied by adding a package name. See [Components](../components.md) and [System context](../system-context.md).

## 2026-10-25 amendment: canonical producer decision

The initial decision above used direct `Submission` output. The accepted latest branch wraps proposals in canonical `ProducerDecision`, a native Pydantic discriminated proposal-or-abstention model. The proposal still contains the same `Submission` and `PlanRevision`; the auditor still outputs `AuditResult`. The old `ProducerOutput.submission` field remains solely for decoding pre-decision persisted payloads, with one canonical projection shared by evidence and evaluation. This changes neither SDK ownership nor evidence authority. Native conformance and small live cohorts are recorded separately in [current plans](../../plans/README.md), with producer diagnostics still unpromoted.
