---
id: SPEC-0079
kind: spec
title: Independent probe authoring in the investigation pipeline
status: accepted
updated: 2026-10-13
related: [SPEC-0078, PLAN-0094, ISSUE-0009]
---

# Independent probe authoring in the investigation pipeline

## Goal and scope

Adopt the user's selected independent control and exploit authoring roles in the production investigation path. Keep exactly two native tests through existing production seams across languages, frameworks and CWEs. The control checks ordinary benign behavior on both revisions. The exploit supplies the reported adversarial condition and asserts the required safety property, so an unsafe implementation fails the assertion. The independent authoring comparison in [PLAN-0093](../plans/PLAN-0093-unit-test-observation.md) remains historical evidence, not proof that splitting improves all cases.

The six agent roles are environment, issue identification, test planning, control authoring, exploit authoring and evidence assessment. Assessment has separate outcome-blind validity and post-execution interpretation calls. Runtime selection, freezing, native execution, gate admission, reporting and cleanup remain deterministic. No new coordinator, graph framework, scheduler, recorder system or general repair loop is required.

## Boundaries and design

The native planner provides exactly two test specifications with distinct operator-approved file paths and native identities, source citations, fixture requirements, actual production calls, benign/adversarial inputs, assertions and typed unit observations. Each author receives only its own specification, behavior, identity/path, immutable source and confined environment evidence. Peer draft, peer input and execution results do not enter author inputs. Separate native PydanticAI factories, contexts, skills and budgets preserve role ownership in direct and durable execution; explicit inference keys select each role.

Each author reads source and writes exactly its own approved file. It returns a draft with assertion line anchors and limitations, or a typed blocker. Trusted code checks current-run source reads, admitted writes, immutable input binding and line-anchor bounds, then freezes the two-file patch. These structural checks do not prove semantic validity. Authors do not execute development tests, choose successors or approve their own output. The old joint factory and frozen evals may remain available for historical comparison; the current production route does not fall back to joint authoring.

A fresh assessment call reviews only the reported condition, plan, frozen patch and captured source for each revision before investigation execution. It must cite the actual production binding, input/preconditions, asserted property and substituted dependencies for each probe. Trusted code binds that review to source, plan and patch identities. The later interpretation call consumes the immutable review and native outcomes without rewriting it. Copied or mocked targets, vacuous assertions, benign exploit inputs, unavailable seams and fixture/policy denials cannot establish application safety.

Dependency mocks/fakes/fixtures are ordinary unit-test tools when they preserve the production logic owning the property. A recording database or process client can establish argument construction; database engine or shell execution behavior requires scoped integration evidence if that behavior is the reported property. Optional witnesses can support a valid unit observation. Missing low-level telemetry alone cannot block it. Witness-only legacy plans remain explicitly unsupported by the current split route, rather than silently acquiring unit validity.

Native execution uses the same frozen pair on each investigated revision and retains both per-probe outcomes, source/environment identities, failure details and cleanup. Host fixtures execute only exact operator-reviewed bytes. Generated workload tests require the admitted sandbox execution route. All authorities, policies, pins and budgets remain operator-owned.

## Acceptance and validation

- Independent author projections exclude peer specification, identity, draft and outcomes; each role writes only its own file and supplies source-grounded assertion anchors.
- Direct and durable paths use the same factories/contracts and explicit role provider keys; failures, retries and budgets remain attributable.
- Validity occurs before native execution and remains frozen during disposition. Two actual native outcomes per revision are required; failed control, skip, unknown delivery or denial cannot prove a fix.
- Host-isolated frozen evaluations cover every role in execution order, with per-stage correctness, contract, trajectory, grounding, robustness/security and efficiency metrics. Native execution qualification is reported separately from injected deterministic port observations.
- Curated multilingual coverage reuses existing sources and native conventions where possible. Unsupported runtimes/frameworks and unavailable native baselines stay explicit. Exactly two probes and generic policy apply to all cases; new corpus examples do not admit a runtime.
- Preserve original datasets, promoted baselines, comparison reports, source snapshots and saved durable histories. Version new fixtures and record their qualification envelope.

A broad whole-tree offline checkpoint passed (2,274 passed, 6 skipped); final source/budget alignment and ordered live stage baselines remain pending. Focused split host fixture checks and scripted native composition are recorded in [PLAN-0094](../plans/PLAN-0094-independent-probe-authoring.md). The production semantic validity gate under ISSUE-0009 remains unresolved until the new reviewed evidence establishes its acceptance criteria.

## Decisions and open questions

The user authorized promotion of independent roles and a start-to-finish baseline walk, including targeted multilingual/framework examples and negative semantic cases. Separate budgets and explicit role ownership implement that direction; prior correctness ties do not become a quality superiority claim. Reuse PydanticAI, Temporal, Pydantic Evals and existing native ports. Shared probe-authoring code has two concrete consumers and does not add orchestration authority.

Broad runtime/provider/durable qualification, general semantic-review calibration and live corpus completeness remain evidence questions. Publication and deployment retain existing session authorization boundaries; this spec introduces no additional approval gate.
