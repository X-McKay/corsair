# ADR 0004: Payload pair, coverage-gated kernel, and six labels

- **Date:** 2026-10-25
- **Status:** Accepted — implemented; items the owner may revisit are listed in [PLAN-0001](../../plans/active/PLAN-0001-pilot-plan-and-open-decisions.md)

## Context

Corsair must turn a model's understanding of a finding into evidence without letting a model author exploit code, run anything, or decide the result. The costliest error for a finding validator is a false negative, so the negative label must be the hardest to reach. The result also needs an explicit state for a case that could not be exercised, so that an unrunnable case is never read as evidence either way.

Three constraints shape the design. The repository's rules forbid an agent from authoring executable exploit code. The auditor must stay outcome-blind so that two models cannot agree their way to a label. Scope (component versus application) is a property of the finding, not of the label.

## Decision

**Payload pair, not probe module.** The producer proposes one JSON payload pair, a benign payload and an exploit payload for the same target seam, as canonical `ProducerDecision` data. The kernel owns the operator-reviewed recipe, materializes the probe from recipe plus payloads at run time, and runs it. The producer never writes code, never runs anything, and never sees an outcome. The executable is operator-owned; the model contributes data.

**Six labels.** The result label is one of `EXPLOIT_DEMONSTRATED`, `COMPONENT_EXPLOIT_DEMONSTRATED`, `EXPLOIT_NOT_DEMONSTRATED`, `INCONCLUSIVE`, `UNABLE_TO_RUN`, and `ERROR`. `EXPLOIT_DEMONSTRATED` and `COMPONENT_EXPLOIT_DEMONSTRATED` differ only in scope: both require the same genuine control-versus-exploit differential (target-line coverage in both runs, accepted audit); the component label is awarded when the finding claimed application scope but only the component seam was exercised, so reachability to the claimed application entry point was not established. The scope signal is code-decided from `finding.claim_scope` and the recipe that binds the component seam, never a model judgment, and merely reaching a sink is never either label. `INCONCLUSIVE` means no demonstration settled at any scope. Developer next step for `COMPONENT_EXPLOIT_DEMONSTRATED`: harden the component or prove an upstream guard blocks the input.

**Exact target-line coverage gate.** Control and exploit come from one differential run pair differing only in payload. Each run must show that the finding's exact target line executed. A pair with an uncovered run is discarded as `INCONCLUSIVE` and counts toward nothing. Coverage is checked before any observation reaches `evidence_agreement`, `blind_audit`, or the verdict table.

**Two independent sessions for a negative.** `EXPLOIT_NOT_DEMONSTRATED` requires at least `negative_threshold = 2` independent producer sessions, each producing a coverage-valid, non-rejected pair whose exploit run did not demonstrate the condition. `EXPLOIT_DEMONSTRATED` rests on the control-versus-exploit differential on the vulnerable revision alone: a healthy control, a covered exploit run that demonstrated the condition, and a non-rejecting audit. A fixed revision is optional confirmation, not a precondition. When one is supplied, the label is withheld only if the exploit still demonstrates on the fix revision (`FixStatus.NOT_BLOCKED`), which signals an incomplete fix or a suspect demonstration; a fix revision that blocks the demonstration confirms the label, and one that cannot be cleanly evaluated leaves the vulnerable-revision differential standing.

**One ADK episode per Temporal activity.** Each producer or auditor episode is one ordinary activity with a single attempt ([ADR 0001](0001-sdk-owned-durable-rounds.md)); the experimental ADK Temporal plugin is not used.

The verdict is decided by [`policies/verdicts.py`](../../../src/corsair/policies/verdicts.py) in the fixed gate order `target_binding`, `ast_guard`, `build_replay`, `control_run` + `control_coverage`, `exploit_run` + `exploit_coverage`, `evidence_agreement`, `blind_audit`, `fixed_differential`. The auditor has no tools and can only reject.

## Alternatives considered

1. **Producer writes a probe module.** More expressive, but it makes a model the author of executable exploit code, which the repository's rules prohibit, and it moves assertion authorship from the operator to the model. It stays an open item with the owner, not a pilot option.
2. **Three or four labels with scope encoded in the label.** Folding component/application scope into the label hides the evidence behind a qualifier and leaves no label for a case that could not run.
3. **Line-range or file-level coverage.** Cheaper to satisfy, but a run that executed the file without reaching the finding's line says nothing about that finding and reopens the false-negative path.
4. **One session for a negative.** Faster, but a single producer miss would become a negative certificate. One session yields `INCONCLUSIVE`.
5. **An accepting auditor.** An auditor that can accept becomes a second verdict authority; a reject-only auditor can only make the kernel more conservative.
6. **The ADK Temporal plugin.** It would checkpoint inside an episode but move the persistence, testing and failure boundary into the plugin; the pilot keeps the episode as the durable unit.

## Consequences

The producer's output surface is data, which keeps the agent evaluable in isolation with fixture-answered ports and keeps exploit authorship with the operator-reviewed recipe. Recipe coverage, not model creativity, bounds what the pilot can validate; a finding without a matching recipe is `UNABLE_TO_RUN`, not a model guess.

A negative label costs at least two producer sessions and two differential pairs; a positive label rests on one vulnerable-revision differential pair, with an optional fixed-revision pair as confirmation when a fix is supplied. That is the intended price of making a false `EXPLOIT_NOT_DEMONSTRATED` the hardest outcome to produce. Evaluation datasets and oracles use the six labels.

The decision does not change contract/port boundaries ([ADR 0002](0002-pydantic-contracts-and-ports.md)) or evidence immutability ([ADR 0003](0003-immutable-native-evidence.md)). See [Data flow](../data-flow.md) for the gate order and verdict table and [Security architecture](../security.md) for the non-negotiables.
