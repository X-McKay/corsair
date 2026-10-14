---
id: PLAN-0095
kind: plan
title: Native agent manifests and operator policy
status: complete
updated: 2026-10-14
related: [SPEC-0080, IDEA-0010, SPEC-0079, PLAN-0094]
---

# Native agent manifests and operator policy

## Objective and dependencies

Implement the user-authorized [SPEC-0080](../specs/SPEC-0080-native-agent-manifests.md) migration using native PydanticAI 2.55.0 specs with explicit Python capability instances in the current PR. The user's later instruction supersedes the earlier after-PR dependency. PLAN-0094 retains completed and interrupted baselines; preserve their source/data/receipt identities and measure migrated source separately. Helper, policy and per-role migrations have separate owners; coordinate actual interfaces before changing each package.

## Steps

- [x] Reconcile the new user scope and preserve the existing baseline references, completed results and stopped partial attempts; do not relabel them as migrated-source measurements.
- [x] Verify the pinned native spec schema and loading behavior; map only supported package instruction/capability fields. Resolve any descriptive metadata need explicitly; do not assume external harness metadata or instrumentation flags are native.
- [x] Define the minimal operator policy surface using existing `InferenceConfig` and `CompositionBudget` validation, with one truth for profiles/settings/ceilings/retries. Preserve explicit JSON compatibility; add typed operator YAML only if needed, without new credential/provider machinery.
- [x] Freeze existing control/exploit rendered instructions, typed contracts, validators, tool/capability schemas, request settings, retries and derived limits. Introduce trusted package manifests and a tiny native construction helper for those two consumers.
- [x] Prove source/configuration/authority parity in direct, durable and isolated modes; retain old histories and run appropriate new history/replay checks. Check rejection of untrusted repository manifests, unknown fields/capabilities/imports and policy mutation.
- [x] Account for frozen pilot measurements and separate body/anchor review. Fresh post-manifest live comparisons are explicitly deferred by the user; no new model quality claim.
- [x] Migrate each remaining role independently with parity checks; all seven factories complete. Fresh live comparisons deferred by the user.
- [x] Review final changes, record manifest/policy/factory/tool/skill hashes and effective limits in receipts, update CURRENT and prepare the handoff. Claim only the checked scope.

## Validation and progress

Implementation complete under the later user authorization; live qualification deferred by the latest instruction. The pinned 2.55.0 SDK's `AgentSpec`, `Agent.from_spec()` and `Agent.from_file()` were locally verified during IDEA-0010 research. That observation establishes API availability, not a manifest migration or runtime admission. Helper/policy implementation and final offline/native-construction parity checks are complete. Fresh final-source live comparisons are **UNRUN / user-deferred**; no role quality or composition admission follows from API availability.

Existing baseline results and gaps stay attributable in PLAN-0094 and the public baseline report. This documentation lane performs no endpoint or source/configuration implementation. Helper/policy owners implement those boundaries; their actual tests, migrated factories and source identities will be appended here. Offline record/link guards will validate these new records separately from implementation evidence.

## Decisions and next action

Use native construction plus a small helper, rather than custom inheritance. Keep typed contracts, validators, authority, skills and durability in their existing owners; package manifests cannot supply arbitrary code or broaden tools. Operator policy is immutable to investigated agents and resolves through the existing provider/budget machinery. Keep exactly two native probes, independent authors and immutable outcome-blind validity; no marker protocol or new recorder requirement.

Next: land the trusted native helper and operator-policy resolution, verify the control/exploit parity pilot, then migrate each role independently with its affected checks and separately identified measurements. Stop a role migration on changed instructions, tool authority, validators, effective settings or incompatible histories; preserve independent completed work. Public PR/deployment actions retain their existing session authorization boundaries.


### Source migration checkpoint

The canonical `corsair-agent-scaffold` skill has been updated alongside the package convention to require trusted package `agent.yaml` and one owned source for instructions/skills, while keeping typed Python contracts, validators, tools and native durability explicit. Configuration examples select both independent author keys and retain the historical `authoring` profile. Existing explicit JSON configuration remains operator-owned and supported; typed YAML extends the same inference/budget models, not a second resolver.

Source inspection confirms `load_agent_spec(role)` uses fixed trusted role paths and the original `build_agent(...)` wrapper delegated explicit Python authority to native `Agent.from_spec()`; the accepted amendment below removes that wrapper. Policy exports `load_budget(Path | None)`, `DEFAULT_BUDGET`, `BUDGET_POLICY_SHA256` and `budget_sha256(...)`; explicit overrides are flat `CompositionBudget` JSON/YAML. The policy owner reports 45 targeted policy/provider/direct/durable checks passed; final shared validation passes and migrated-role live baselines are user-deferred. No new base-class hierarchy, arbitrary capability import, investigated-repository manifest, marker protocol or agent-editable operator policy is authorized. Preserve exactly both native probes and immutable outcome-blind validity. New receipt identities must bind resolved manifest/policy/factory/tool/skill content and effective configuration/limits; a file name or version alone is insufficient.

Documentation checkpoint: `tests/configuration/test_development_workflow.py` passed **5/5** after the native manifest/operator-policy documentation update; `git diff --check` passed. These checks validate records and formatting, not runtime or agent qualification.

### Final-source checkpoint before publication

Implementation is complete for the split route and all seven native-manifest factory variants, including repository identification; shared helper and operator policy are implemented with byte-parity evidence. Final instruction/skill ownership cleanup and receipt identity additions are underway. Root's pre-cleanup full suite: **2,326 passed, six skipped, ten warnings in 39.71 seconds**. Scripted environment16/16, identification8/8, planning5/5, control8/8, exploit8/8, validity7/7, final disposition4/4 and chain5/5 pass. Invalid `unit-test` CLI set selection was rejected before model calls; corrected `unit` passed.

Read corrected pre-manifest summaries: environment4/8 clean (two task failures), identification8/8, planning1/5 clean (five typed contracts, four adversarial-input oracle failures). Historical54-case assessment stopped with14 retained attempts and no aggregate verdict. Preserve all original source/results and reassessment labels. Final shared checks pass; serialized final-source live measurements are unrun and user-deferred; no semantic-review, wider runtime or composition admission is claimed. Continue from [HANDOFF-0130](../handoffs/HANDOFF-0130-native-manifest-baseline-checkpoint.md).

Final publication checkpoint (2026-10-13): implementation and identity/ownership cleanup complete. Root reports full offline **2,329 passed, six skipped, ten warnings in 51.95 seconds**, final targeted **60 passed**, and seven native factory parity **22 passed**. Final scripted suites pass: environment16/16, identification8/8, planning5/5, each author8/8, validity7/7, final disposition4/4 and chain5/5. Offline wheel inspection confirms ten YAML/shared-skill assets byte-equal to current source (`native-yaml-wheel-final-check.json` private receipt); the431-file source-freeze manifest remains ignored. These are offline/parity/fixture claims, not model quality or composition qualification.

The user explicitly deferred fresh post-manifest live baselines and requested the PR now. All seven planned live jobs are **UNRUN / deferred**. Automatic approval review rejected their earlier launch before any model calls. Corrected pre-manifest environment4/8, identification8/8 and planning1/5 remain historical measurements. ISSUE-0009 stays open. No endpoint calls occurred in this documentation lane; raw `.runs` exports remain private.

## Accepted native SDK simplification amendment

The user accepts retaining the full current agent-package structure while designing around out-of-box PydanticAI. In PR132 each factory directly uses native `AgentSpec.from_file(...)` at a fixed trusted package path and `Agent.from_spec(...)` with explicit Python capabilities, model, typed contracts/validators, retries and native durability. Remove custom package selectors, construction wrappers and `capability_selection` metadata. Native YAML metadata keeps descriptive `config_version`/`prompt_version`. `factory_identity` remains provenance-only file hashing, not construction.

Owned skill files and current eager procedure loading remain. SDK-agnostic exploration, generic SDK schemas, Google adapters and progressive loading are deferred; optional future deferment must use native SDK facilities. Exactly two probes, independent authors and immutable outcome-blind validity remain unchanged. Prior parity/checks and deferred live baselines retain their original source identities. Amendment implementation and offline validation are complete as recorded below; existing PR update is authorized, merge is not.

The subsequent user question identifies upstream Harness `Skills` as the intended progressive-disclosure mechanism. Verified current upstream documentation describes native catalogs/load_capability and a separate skills-extra dependency; local inspection found core 2.55.0 installed and neither Harness nor Google ADK installed. No custom loader or SDK abstraction should be introduced. This native-construction amendment retains eager procedure behavior for parity; a dependency-compatible native Skills integration remains a distinct next boundary, not an implemented feature. Bundled resource reading/script execution are not supplied by Skills itself.

Amended-source validation: seven native offer captures preserve instructions, tools, schemas, dependencies and retries (13 native/package checks passed); 25 focused author/composition/durable-payload checks passed. Full offline command using the existing review venv and `pytest -q -n4 tests/configuration tests/unit tests/agents tests/temporal/test_fixture_contracts.py tests/temporal/test_issue_analysis_composition.py tests/temporal/test_chain_composition.py`: **2323 passed, 6 skipped, 10 warnings in 48.76s**. Removed custom-loader/selector tests are not retained as claims of native security enforcement. No live model calls occurred; fresh live baselines remain user-deferred. Native Harness Skills is the intended next feature boundary, with dependency compatibility and actual disclosure/validator behavior still unqualified.

Final native-direct scripted registry runs passed: environment16/16, identification8/8, planning5/5, control8/8, exploit8/8, validity7/7, final-unit4/4, fixture chain5/5. User's follow-up identifies Coder/Harness reuse as valuable across agents; upstream review confirms its modular components and broader default tools. Next bounded design work should audit Harness Skills/FileSystem/Shell/context features against current ports before new bespoke functionality. Harness integration itself remains unimplemented and version/workspace/evidence behavior unqualified; no full Coder default was enabled by this simplification.
