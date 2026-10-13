# Agent evaluations and acceptance

Evaluate each agent against its objective and authority, then evaluate its handoffs and the complete graph. Retain outcome, trajectory, consistency, and performance results separately; a single average cannot admit an unsupported security conclusion.

## Evaluation types

| Type | Measurement | Method |
| --- | --- | --- |
| Task correctness | Objective achieved against reviewed behavior | Deterministic oracle or real execution; calibrated semantic rubric where needed |
| Contract adherence | Required fields, scope, exact two-test artifact, valid references | Pydantic validation and focused deterministic checks |
| Trajectory | Required actions, ordering constraints, repeated ineffective actions, forbidden paths | Native trajectory/span evaluators and application invariants |
| Tool correctness | Appropriate tools, module/revision arguments, authority | Native tool/argument checks and adapter receipts |
| Grounding | Citations resolve; conclusions follow from observed evidence | Deterministic citation checks plus reviewed semantic assessment |
| Consistency | Repeat variability, equivalent-input stability, evidence sensitivity | Repeated cases and controlled input variants |
| Robustness | Missing facts, contradictory results, operational failures | Deliberate failure fixtures with expected dispositions |
| Security | Instruction injection, disallowed writes/egress, authority expansion | Adversarial fixtures and actual sandbox qualification |
| Durability | Recovery, cancellation, no blind duplicate dispatch | Temporal integration and recorded-history replay tests |
| Efficiency | Latency, tokens, requests, tools, retries, resources | Native usage, traces, SDK metrics, and evaluation reports |
| Composition | Valid handoffs, preserved meaning, correct graph branches | Contract integration and end-to-end reviewed cases |
| Provider/runtime compatibility | Required behavior across selected providers and run modes | Same cases and contracts, separately reported configurations |

Trajectory checks enforce meaningful constraints, not one prescribed shell sequence. Valid alternative setup recipes must remain admissible. Evaluate observable tool actions and evidence rather than assuming access to private model reasoning.

## Native implementation

Use Pydantic Evals datasets, repeated runs, reports, and deterministic evaluators. Reuse `TrajectoryMatch`, `ToolCorrectness`, `ArgumentCorrectness`, `MaxToolCalls`, `MaxModelRequests`, and span predicates when the pinned SDK supports the needed semantics. Use `TestModel`, `FunctionModel`, dependency/toolset overrides, and pytest for deterministic agent tests. Temporal integration uses native test environments and replayers.

Trajectory/span evaluators capture local spans with the Logfire SDK without requiring a hosted account. They do not observe every provider-native operation. Qualify trace coverage separately in direct and durable modes, including failed calls and retry attempts. Missing traces produce an evaluation infrastructure/coverage failure; they cannot be scored as evidence that an agent avoided a prohibited action.

Use post-run trajectory evaluation initially. An online trajectory judge changes behavior, latency, and cost and requires its own qualification before adoption. Model judging supplements execution evidence and does not approve security dispositions by itself.

References: [agentic evaluators](https://pydantic.dev/docs/ai/evals/evaluators/agentic/), [span evaluators](https://pydantic.dev/docs/ai/evals/evaluators/span-based/), [repeated evaluations](https://pydantic.dev/docs/ai/evals/how-to/multi-run/), and [testing](https://pydantic.dev/docs/ai/guides/testing/).

## Per-agent acceptance evidence

| Agent | Primary success evidence | Critical failure cases |
| --- | --- | --- |
| Issue identification | Exact trusted report preservation, correct source symbol/location, scope and justified abstention against frozen curated expectations | Wrong concern, decoy module, invented source, repository instruction injection |
| Environment | Successful fresh replay, relevant build, actual test discovery/execution | Missing dependency, registry/TLS denial, wrong JDK, changes to application behavior |
| Test planning | Exactly two native tests through existing real application seams, unit scope by default; assertions distinguish reviewed behavior at stated scope | Constant assertions, replaced security logic, irrelevant doubles, unnecessary telemetry dependency, sandbox denial treated as fix |
| Test authoring | Exactly two tests exercising intended source and reported condition; control passes both; relevant security assertion fails baseline and passes fixed | Skips, fake runner output, unreachable target, altered behavior, inappropriate dependency double, stale results |
| Evidence assessment | Correct scoped disposition and limitations from frozen evidence | Failed control, incomplete delivery, contradictory results, ungrounded fix/refutation |

Fixtures include real repositories and minimal adversarial cases. Gold labels, vulnerable/fixed variant identities, and evaluator-only tests remain outside agent-visible source. Separate development cases from held-out cases; do not repeatedly tune prompts against the held-out answer key.

The [benchmark dataset plan](benchmark-datasets.md) identifies public sources and 50 metadata-reviewed candidate issue pairs, ten per ecosystem. Candidates are not qualified cases. Admit each pair through its licensing, environment, two-test oracle, fresh replay, and policy-interference gates before scoring live-agent security correctness. Benchmark expansion does not automatically extend the initial runtime support envelope.

## Unit-test evidence acceptance

Evaluate planning, authoring and disposition against the same language-independent rules in the [investigation contract](investigation-contract.md). Existing native test seams, return values, exceptions, fixture state and recording dependency doubles are first-class observations. Include a valid query-construction case with a recording database double and no database telemetry, alongside negative cases that replace the query-building logic, never call the target, assert an irrelevant property, or treat arbitrary failure as safe rejection. The valid case must remain admissible without a new recorder; the invalid cases must remain inconclusive.

Keep independent test-validity review separate from native discovery and result parsing. A generated assertion passing is insufficient semantic proof. Optional witnesses need their own behavior-preservation and coverage checks, including unobserved effects and empty traces; their availability must not silently change the supported scope. Qualification remains specific to executed runtimes/frameworks and measured properties.

## Consistency and robustness

Repeat the same case with identical configuration and a fresh workspace to measure variability. Compare semantic dispositions and preconditions, not wording. Report repeat correctness and agreement together; consistently wrong answers fail correctness.

Equivalent-input variants change irrelevant formatting or paraphrase the finding. Meaningful evidence variants change a control result, receipt completeness, or source guard and should change the interpretation accordingly. Provider comparisons are separate evaluations, not a requirement that different models produce identical text.

Preserve every repeat and failure. An evaluation rerun is a new attempt, not a hidden retry that replaces an unfavorable result. Lock case set, model settings, runtime, backend, and concurrency for comparisons. Report sample counts and uncertainty where the sample supports it. Small smoke suites cannot establish reliable tail-latency or population error estimates.

## Report schema

An evaluation report includes candidate identity, SDK/runtime versions, dataset and rubric versions, model configuration/revision when available, modes, concurrency, cases attempted, repeats, per-case dimension scores, reasons, trace/artifact references, operational failure classification, and performance metrics.

Keep these counts distinct:

- Attempted, completed, blocked, failed, unknown, and unsupported cases.
- Correct reproduction, correct scoped refutation, unsupported conclusive disposition, and inconclusive outcome.
- Evaluator failures and missing telemetry coverage.
- Provider, sandbox, dependency, and agent failures.

Show denominators both across all attempted cases and within completed supported cases. Do not remove infrastructure failures to improve apparent success. Track token and cost coverage so missing observations do not bias efficiency comparisons.

## Acceptance gates

Before a component is connected, all deterministic contract and required negative-path tests pass; its actual SDK path is exercised; failure evidence is attributable; and its objective has a reviewed evaluation baseline. Mocks do not qualify a live adapter.

For initial fixture qualification, require all mandatory vulnerable/fixed cases to behave as expected and zero unsupported conclusive dispositions. These are finite-suite gates, not claims of universal safety. Record achieved coverage and limits. Set live-agent success, latency, token, and retry regression thresholds after collecting a repeat baseline; freeze those thresholds before evaluating a candidate change.

Change an agent locally first, run its relevant isolated suite, then affected contract consumers, then a small end-to-end regression suite. Shared contract, runtime, or policy changes require broader checks determined by artifact invalidation rules.

The narrow identification contract in SPEC-0024 uses deterministic curated selection oracles rather than an LLM judge. They test known case expectations and do not prove arbitrary unseen-source semantics. Conditional setup, preconditions and application effects remain test-planning/execution responsibilities; end-to-end disposition criteria are unchanged. Historical hypothesis and auxiliary-reviewer evaluations remain bound to their original contracts.
