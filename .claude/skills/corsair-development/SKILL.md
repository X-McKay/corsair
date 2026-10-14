---
name: corsair-development
description: Use when planning, implementing, debugging, or resuming development in the Corsair repository. Follow the shared principles, bounded component workflow, standard work records, progressive qualification, and proportionate validation.
---

# Corsair development

Resolve paths from the repository root. Read `AGENTS.md`, `docs/development/README.md` and `docs/development/CURRENT.md` first. Skills guide work; they do not add authority or approval requirements.

## Resume and define the change

1. Inspect the branch, working tree and relevant source. Read the active plan, linked issue/spec and latest handoff. Reconcile stale context with actual files and evidence before acting.
2. State the bounded objective and failing behavior or acceptance criterion. Locate the current milestone gate and affected component. Preserve unrelated edits.
3. Reuse an existing work record where possible. For substantial behavior/boundary changes, create a spec and implementation plan from `docs/development/templates/`. Ideas are optional and do not authorize implementation. Small corrections can update an existing plan/issue without new paperwork.
4. Verify SDK capabilities and pinned versions before designing a wrapper. Record why native functionality is insufficient if bespoke code is necessary. Keep contract changes, authority, mode/provider differences, failure attribution and validation explicit.

## Implement progressively

1. Make the smallest independently reviewable change. Keep the current plan's ordered steps, decisions and validation notes up to date.
2. Exercise the component alone first. Use native test/override facilities for contracts and real qualification for external boundaries. Do not hide an unavailable live prerequisite with a mock or fallback.
3. For agent changes, select relevant evaluation dimensions from `docs/development/specs/SPEC-0082-corsair-v2-architecture.md` (its eval layout and baselines). Use saved inputs, frozen cases and native instrumentation; record modes, repeat counts, usage/trace coverage and regression evidence.
4. When blocked, retain the command/native error and evidence reference, open/update the repository issue, and mark the plan blocked. Continue useful authorized work that does not depend on the missing gate. Do not add undocumented environment patches or weaken acceptance.

## Investigation changes

Default to exactly two native unit tests around existing real application seams, for every language/framework/CWE. Plans and authoring must identify the intended source, reported condition, benign/adversarial inputs, relevant assertions, observation boundary and dependency-double limits. A recording database or process double can establish construction behavior when the real construction logic remains exercised; integration evidence is required for engine or shell behavior. Review frozen tests in a separate outcome-blind call before investigation execution; later disposition must consume the source/plan/patch-bound review without rewriting it. Check real target calls, non-vacuous assertions and dependency boundaries for both probes. Matching observation kinds or differing revision results alone do not prove calibration or source linkage. Optional witnesses may strengthen evidence but missing low-level telemetry alone must not block a sound test. Passing generated assertions alone do not prove validity; retain review and calibration evidence. Prefer this shared contract over a new language-specific recorder.

## Validate and record

- Run `make test-config` for fast repository guards. Run affected component/live/replay/evaluation checks when their boundary changes. Do not rerun Docker qualification for a documentation-only change.
- Use `corsair-review` for the final review. Record actual commands and outcomes, including blocked, failed and unrun checks; preserve supported limits.
- Update the affected spec/plan/issue and `CURRENT.md`. A completed implementation plan can still leave runtime qualification outstanding if that limit is explicitly part of its scope.
- Use `corsair-handoff` before ending substantial work. Include concrete next actions and stop conditions. Commit/push only within the user's authorization; never publish raw run/state evidence.

Examples: qualify the current platform gate; implement one sandbox adapter method; change one agent prompt and compare its isolated evaluations; investigate a native build failure without altering sandbox policy.

For validity-review changes, require cited findings for each probe’s actual production binding, inputs/preconditions, asserted property and substituted dependencies. Derive overall validity from both probes. A copied target is invalid even if identical; a benign input is not an exploit because its test is named one. In evaluations, separate semantic false approvals from contract failures and evaluator defects, preserve old measurements when versioning corrections, and distinguish fixture runner responses from actual generated-test execution.

For the current independent probe pipeline, preserve six roles (environment, identification, planning, control authoring, exploit authoring and assessment), with separate outcome-blind validity and result calls of assessment. Each author sees only its own specification, identity/path, behavior and cited immutable source, writes its own file and returns source-only assertion anchors under its own operator budget. Keep the control an ordinary benign behavior check and the exploit a true reported-condition adversarial safety test. Neither peer drafts nor execution outcomes enter author context. Trusted structural admission does not establish semantic validity; freeze the pair, review both actual source bindings/inputs/assertions/doubles, then require both native outcomes on each revision. Historical joint-author/witness-only measurements remain historical; current split composition does not silently fall back or acquire validity from them. Evaluate each role and both assessment call modes separately across admitted native frameworks, while distinguishing injected host port observations, reviewed native fixtures and live runtime qualification.

For native agent manifests/operator policy, follow the package convention and SPEC-0080/PLAN-0095. Load only fixed trusted package specs with native `AgentSpec.from_file(...)` and `Agent.from_spec(...)`, passing explicit Python capability instances; literal static instructions have one manifest owner, procedure has its skill owner, and Python retains typed contracts, output/current-run validators, restricted tools and native durability. Use explicit operator inference/budget resolution with one profile/ceiling/retry truth and legacy JSON compatibility. Reject repository-controlled manifests, custom capability selectors/settings fields, arbitrary imports and marker verdict protocols. Preserve frozen pre-migration results/histories; check complete instruction/tool/schema/settings/effective-limit parity, then evaluate each migrated role separately with resolved manifest/policy/factory identities. Record missing telemetry and runtime/provider/durable qualification as unknown until actual evidence admits them.

Keep the full agent-package structure. YAML metadata is descriptive config/prompt versions, not capability authority. `factory_identity` is provenance-only; no custom construction helper or SDK-agnostic schema. Current factories use pinned native Harness Skills for progressive disclosure through read-only primary package workspaces. Retain explicit domain toolsets, native UsageLimits and evidence-bound validators; no custom skill loader. SDK workspaces are not sandbox isolation.
