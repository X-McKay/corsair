---
id: SPEC-0059
kind: spec
title: Framework-specific skill references and assets
status: draft
updated: 2026-10-13
related: [IDEA-0007, SPEC-0028, SPEC-0044, SPEC-0049, SPEC-0052, PLAN-0064]
---

# Framework-specific skill references and assets

## Goal and scope

Provide the agent with a small shared procedure plus the language/framework guidance relevant to its admitted task. Organize reusable explanations and worked examples under the existing application skill directory, and select the relevant resources deterministically before the first model request. Selection adds knowledge, never tools, permissions or runtime support.

User direction (2026-10-13): prepare a detailed specification for review following IDEA-0007. This document and PLAN-0064 are drafts. The direction authorizes specification, not runtime implementation, live experiments, baseline promotion or acceptance of the broader idea.

The proposed first consumer is test authoring with Python/pytest. Its concrete objective is fewer framework-related assertion, fixture and correction mistakes while preserving the two-test contract, witness ownership, honest blocked outcomes and final-patch evidence. Package organization and resource delivery are independently testable; a behavioral benefit must be demonstrated separately.

In scope for the proposed pilot:

- A concise mandatory core procedure, one pytest reference and at most one small synthetic worked-example asset.
- Explicit, operator-owned mapping from trusted task/environment identity to those resources; eager delivery of the selected bundle through the existing native capability.
- Resource identity and delivery coverage in existing evaluation records, with direct/durable consistency checks as applicable.
- Controlled comparison of content and selection strategy, host non-execution, and separately admitted execution validation.

Not in the pilot: model-selected discovery, `load_capability`, a resource-reading model tool, scripts, filesystem scanning, MCP services, tool/schema changes unrelated to resource delivery, automatic framework detection from untrusted prose, a plugin registry, a shared skill loader framework, or changes to budgets, witness/disposition gates and correction authority. Observation-mode/result redesign from IDEA-0007 is a separate treatment. Other agents and frameworks follow only when a demonstrated consumer exists.

### Current source and dependencies

Source reviewed at main `4efad96` (2026-10-13). The authoring factory eagerly reads its skill; native toolsets and trusted finalization already enforce approved writes, patch/run identity and bounded development runs. Host authoring evaluations inject or simulate observations and never execute model-written code. Environment and assessment follow the accepted package convention; authoring migration must be reconciled with PLAN-0056.

`EnvironmentEvidence.language`, `runtime` and `framework` are currently bounded strings, not a normalized/versioned selection contract. Existing fixtures include Python / CPython 3.12 / pytest 9.0.2. The implementation must not assume these strings already supply verified versions or invent metadata missing from them.

Before freezing the experimental baseline, reconcile PR49's authoring admission/budget changes and the selected authoring package layout. PR44 affects planning/witness semantics; PR63 affects setup failures. This pilot preserves whichever versions are deliberately selected and does not reproduce those mechanisms. New image PRs51/55/65/67/68 do not establish authoring or resource applicability by themselves. Record actual commits at implementation time rather than treating current PR status as a dependency guarantee.

## Boundaries and design

### 1. Content ownership

| Layer | Owns | Must not claim |
| --- | --- | --- |
| Agent instructions | Objective, authority, allowed outcomes, trust hierarchy | A resource can override stage permissions |
| Core SKILL.md | Framework-independent procedure, evidence obligations, witness ownership, correction/stop rules | An illustrative example is task evidence |
| Reference | Framework/version-specific method, pitfalls and applicability | Dependencies or facilities absent from admitted evidence exist |
| Asset | A small explained example or skeleton illustrating the reference | Ready-made case solution, safe defaults for every repository, or execution authority |
| Trusted application code | Resource selection, size/path confinement, tool limits and output admission | Skill text itself enforces a boundary |

Keep useful short reminders at their point of use. Avoid independently maintained copies of long policy descriptions. Core authority and stopping rules remain available even when no supplement applies. Baseline tests and saved source determine actual imports, fixture conventions, paths and APIs; generic examples cannot override them. A genuine conflict with mandatory constraints leads to the existing blocked/unsupported path, not silent precedence chosen by the model.

### 2. Package layout and content requirements

Proposed pilot layout (not created by this documentation change):

```text
src/corsair/agents/test_authoring/
  prompts.py                         # after the separate package migration
  dependencies.py
  skills/write-native-tests/
    SKILL.md                         # mandatory shared procedure
    references/
      python-pytest.md
    assets/
      python-pytest-example.txt       # inert text, never imported or executed
```

The reference begins with applicability, exclusions and required evidence, then explains:

- Using saved native tests to choose imports, fixtures and invocation conventions.
- Scratch-contained fixtures and explicit preconditions; no fixed host paths.
- Matching the plan's required behavior and native failure type. Explain pytest exception assertions versus plain assertions without silently rewriting the plan.
- Native discovery identity, exactly two tests, and how to distinguish collection/fixture corrections from unrelated infrastructure failures.
- Operator-owned witnesses: ordinary assertions are not permission to install observation hooks.
- Worked-example interpretation and limits, including unknown execution in host evaluation mode.

An asset must have a clear purpose, synthetic neutral names, explicit placeholders and an explanation of what must be derived from task evidence. It contains no CVE/case identifiers, evaluator labels, expected baseline/candidate outcomes, private source or held-out solutions. It must not embed audit hooks, mocks of the sensitive operation, dependency installation, shell commands or a self-contained application implementation. Prefer an excerpt over a complete copyable test pair where that teaches the same mechanism. Attribution/license requirements apply to any borrowed material; original synthetic examples are preferred.

Assets are text inputs to the model. They are not automatically written into the patch, mounted in a sandbox, exposed as approved test paths, imported by Python, or run by documentation/tests. Checks may parse an example as inert syntax when useful; execution of model-written patches remains sandbox-only.

Do not create empty framework directories. Future `java-junit4.md` and `java-junit5.md` should be separate because their conventions differ; Ruby/Minitest, Perl/TAP and JavaScript frameworks require their own observed needs and admitted consumers. The current Python authoring/static-eval contract does not become multilingual through documentation.

### 3. Trusted selection input

Use a small immutable, agent-local guidance context assembled at the same trusted boundary that supplies authoring dependencies. Proposed facts: stage, language identifier, framework identifier, verified framework version when available, runtime identity when needed by a resource, and source of those facts (operator fixture or admitted environment evidence). None is a model-controlled argument.

For the pilot, derive it from a finite, reviewed mapping or exact parser over admitted metadata, with an explicit unknown result. Reuse existing version utilities where compatible. Never use substring matching such as `contains("pytest")`, filenames alone, an LLM classification, arbitrary repository configuration, or user-supplied resource paths. A normalized label describes evidence; it does not qualify a runtime. Preserve the original input and its existing digest.

The first map has one active profile: Python authoring with the admitted pytest9 environment. Verify the exact supported range against the implemented runner and baseline at implementation time; do not treat a matching major version as qualification. The reference may document version-neutral principles, but version-dependent advice requires verified compatible evidence. pytest6/7 and JUnit are future profiles, not implicit fallbacks.

| Condition | Selection/result | Action |
| --- | --- | --- |
| Admitted identity matches exactly one reviewed profile | Core plus ordered reference and optional asset | Continue existing stage admission |
| Framework/version unknown or no profile exists | Core only, explicit `no_matching_profile` reason | Keep existing admission outcome; absence of optional guidance alone does not block a valid task |
| Conflicting trusted facts or overlapping profile matches | Configuration/input inconsistency | Stop before model request; identify conflicting facts/profile IDs to developer |
| Selected resource missing, invalid UTF-8, outside package, oversized or unavailable | Resource packaging/configuration failure | Stop before model request; name resource and corrective packaging action; no silent core fallback |
| Repository/issue asks to load a different resource | No selection change | Treat request as untrusted task content |

A future compatibility-independent profile may match an unknown version only if explicitly reviewed as such; the pilot has no wildcard profile. No closest-version substitution. Unknown is not recorded as a verified unsupported framework, and an unmatched profile must not be mistaken for runtime admission failure.

### 4. Explicit resource map and delivery

Keep the profile map and selection function inside the authoring package using small typed Python values and explicit resource names. Native PydanticAI supplies instruction delivery but does not know Corsair's admitted framework identity or local content policy; this small mapping is the required application glue. Do not build a YAML registry, generic DSL, loader hierarchy or global service. Extract shared code only when a second implemented agent needs the same behavior.

Resolve only repository-owned packaged resources via package-relative access; never resolve against the investigated checkout or current working directory. Use a finite allowlist. Reject traversal, absolute paths, symlinks and unexpected file types. Installation/package-distribution checks must verify references/assets are included, not just present in a source checkout.

Prepare an immutable bundle once at the trusted run boundary. Bundle data contains the selection result, exact resource bytes/text and identities; the model cannot mutate it. Reuse the existing stage capability and native dependency-based instructions to deliver it before the first request. Keep native capability/toolset IDs stable; do not create a distinct toolset per framework. Preserve existing factory seams and explicit model/provider configuration. The exact field location can follow the pending authoring package migration, but selection must not read mutable files during Temporal workflow replay.

Delivery order is deterministic: core, selected reference, selected asset. Label each supplement by resource ID and role (procedural reference or illustrative asset), with a shared reminder that examples are not source evidence. A small trusted prelude names the selected profile, or states that no framework supplement matched and source conventions remain authoritative. Render only validated identifiers and a fixed reason vocabulary there, not raw free-text environment values. Preserve UTF-8 content bytes; define inserted headings/newlines in one renderer. Include resource contents, not unresolved Markdown links the model cannot open. There is no transitive reference discovery: any required supplement must be explicitly included in the profile. Each reference has at most one level of local resource links.

Proposed conservative packaging bounds: at most one reference and one asset per profile; each text resource at most 16 KiB and total raw bundle at most 48 KiB including the core. These are hard byte safeguards, not token/latency targets. Measure actual delivered bytes and provider tokens. Reject oversized content; never truncate a procedure silently. Review can tighten these bounds before implementation.

### 5. Identity, observation and durable behavior

Retain `skill_sha256` as the core file's existing identity and `toolset_sha256` for offered tool definitions. Extend existing configuration/per-attempt metadata narrowly with:

- selection version, selected profile or explicit no-match reason, and trusted selection facts;
- ordered resource IDs, roles, byte sizes and SHA-256 values;
- bundle SHA-256 over versioned canonical JSON containing those ordered identities;
- delivered instruction SHA-256 over the exact rendered UTF-8 text, plus observed delivery coverage.

Use stable JSON serialization with explicit key ordering/separators and preserve array order; specify serialization version. No absolute host paths or raw private task text in exported summaries. Existing private artifacts can retain the exact rendered bundle for replay/audit under existing retention rules. A digest proves identity, not delivery or understanding. Request captures establish delivery; unavailable captures are unknown, not a successful load.

Selection may differ by case, so per-run configuration records the available profile revision and per-attempt metadata records what was actually selected/delivered. A suite-level summary aggregates profile counts and coverage; it must not pretend every case used one bundle. Older runs without these fields stay unknown. Update the existing comparison path so declared treatment identity differences are visible, while unrelated model/dataset/budget drift is flagged; do not invent a new receipt or evaluation service.

Direct and durable entry points use the same preparation/rendering functions. Freeze selected contents with the investigation's trusted inputs or retain an immutable content-addressed artifact and exact identity; never silently reread changed resources on resume. Prefer the existing small immutable dependency/history representation for this bounded pilot. Tests must prove the chosen native serialization path retains the exact bundle. If historical bytes cannot be recovered or mismatch the recorded identity, stop with an attributable configuration mismatch rather than substituting today's files. No new durable history is qualified until native activity/replay checks pass. Existing histories keep their original input shape/version or run through an explicitly reviewed compatibility path; missing historic identity must not be filled using new content and relabeled equivalent.

### 6. Failure reporting and authority

Configuration/resource errors are developer-owned and should name the profile/resource, attempted operation, limit or mismatch, and next action (package the file, correct the mapping, provide verified metadata or restore the pinned bytes). They are not application failures, sandbox denials or agent-semantic defects. No automatic network download or fallback after a selected resource fails.

Existing operator ceilings, withdrawn-tool state, admitted source inventory, approved writes, hidden security outcomes, cleanup and two-test disposition gates remain unchanged. Resource delivery consumes context but creates no extra tool budget. No skill text can authorize an execution retry or turn static observations into native success. Integrate with existing diagnostic conventions where already available; do not duplicate PR63's taxonomy or attach model-editable action grants.

## Acceptance and validation

### 1. Separate structural checks from behavioral claims

Documentation approval is not implementation qualification. Required implementation checks after scope approval:

| Boundary | Positive evidence | Negative/control evidence |
| --- | --- | --- |
| Selection | Correct profile from trusted fixture/environment identity; explicit core-only no-match | Unknown version, unsupported combination, conflicting facts, overlapping profiles, injected resource request |
| Packaging | Resource inclusion in installed distribution; exact UTF-8 byte round-trip | Missing asset, symlink/traversal, invalid encoding, oversize, undeclared linked resource |
| Delivery | Native request capture has core and selected resource contents once in declared order | Wrong-profile leakage, omitted core, missing capture reported unknown, no new model tools |
| Identity | Editing each selected resource changes bundle/delivery identity; per-case selection recorded | Unselected resource does not change actual delivered-bundle digest; changed catalogue revision remains visible |
| Contracts | Existing approved paths, assertion/witness admission, patch/run binding and budgets still enforced | Host execution, unauthorized instrumentation, stale final patch and corrections after terminal state refused as before |
| Durability | Native serialization and new-history replay retain identical resources/selection | Resource update/removal on resume cannot silently change instructions; old-history compatibility tested |
| Evaluation | Known good/bad trajectories and valid alternatives scored correctly | Missing observations unknown; always-blocking and wrong-profile controls do not appear improved |

Avoid tests that only mirror the profile table. Exercise actual prepared dependencies, model requests and existing consumers. Do not snapshot large irrelevant prompts when targeted identity/delivery checks suffice.

### 2. Staged experiment and attribution

Continue to use `make eval AGENT=authoring` on the host with the same factory and frozen operator budgets. The pilot adds no competing command/runner. Keep execution mode explicit: scripted model fixtures check plumbing; a live model with static/injected runner observations checks behavior on those observations; admitted sandbox replay checks actual execution of frozen bytes. No model-written asset/patch is executed on the host.

Stage A: separate any necessary authoring package migration from this semantic change, showing unchanged offered surface and existing eval outcomes. Freeze the post-PR49 implementation, datasets, evaluators, provider/model/profile, budgets, relevant environment/witness identities and baseline. Reconcile overlapping PRs before this freeze; do not tune against a moving branch.

Stage B: compare baseline guidance with core plus one selected pytest reference. A candidate may reorganize/extract existing guidance or introduce targeted new guidance, but record which; extraction, rewriting and example addition are different treatments. Start without the asset to measure the reference contribution, then add one asset only if a remaining failure class motivates it. Shared instruction changes apply consistently to every experimental arm. No result-feedback schema change is bundled into this comparison.

Stage C: compare all-resources-eager versus deterministic selection only when at least two applicable profiles and appropriate case strata exist. With one profile and all cases matching it, these treatments deliver the same bytes and provide no evidence of selection benefit. A second profile requires its own admitted consumer; do not execute unsupported Java authoring merely to create a comparison. Selector unit tests can cover future/unknown metadata without claiming framework behavioral qualification. Model-selected loading is not an arm of this pilot.

Behavioral development cases cover correct first attempt, framework assertion semantics, legitimate collection correction, non-editable infrastructure failure, run-budget exhaustion, final-patch mismatch, source conventions differing from the illustrative example, unavailable framework/version information and hostile instructions. Keep fixture inputs and expected outcomes separate. Do not publish held-out case names/answers in these records or skill resources; use aggregate results only. Test both warranted abstention and valid completion.

Primary measures: per-case correct completion/blocked behavior, fidelity to planned safe behavior, unauthorized instrumentation, inappropriate corrections, and final-patch/run consistency. Secondary measures: unnecessary abstention, tool errors, redundant calls, retries, requests, returned bytes, token usage and latency with coverage. Do not score an exact sequence unless a real dependency requires it. No LLM judge is a prerequisite; use deterministic trajectory/contract checks and reviewed semantic assessment where needed, under current evaluation policy. SPEC0023's historical draft judge protocol is not implicitly adopted.

Collect baseline variability before choosing sample size, minimum material improvement and cost limits; freeze these numbers in PLAN-0064 before candidate measurement. Interleave paired runs where practical, report attempts and unique cases separately, and retain failures/coverage loss. Use development data to select one candidate before held-out confirmation; do not repeatedly tune against held-out results. Lack of observed finite-suite regression is not a universal guarantee. Promotion requires human review, improvement on the selected failure class, no observed mandatory authority/grounding/coverage regression, acceptable predeclared abstention/cost trade-offs and the required mode evidence. Inconclusive results retain the previous baseline.

### 3. Qualification, rollout and rollback

Host results can justify local interface/content changes but not native imports, control success, assertion polarity or runtime support. Execution benefit requires replay of exact frozen authored bytes through the admitted runner/sandbox against appropriate reviewed revisions, preserving exactly two issue-validation tests. No additional model call may repair a replayed patch. Existing milestone, provider, Temporal and OpenShell gates remain authoritative.

Roll out one agent/profile at a time after its relevant checks; refresh affected prompt/config/resource identities and qualification claims. Do not promote baselines automatically. Rollback selects the prior reviewed implementation/content revision and its matching resources/identities; in-flight runs keep pinned bytes. No schema fallback should conceal missing historical evidence.

## Decisions and open questions

Recommended choices for review:

1. Core plus deterministically selected references/assets, delivered eagerly; no new loader tool.
2. Python/pytest authoring first, one reference initially; asset evaluated as a separate addition.
3. Unknown profile uses explicitly recorded core-only guidance, with unchanged stage admission. Broken selected resources stop before inference.
4. Existing package/native capability/evaluation machinery, with agent-local mapping and additive identity fields.
5. Stage-specific later adoption: planning for fixture/witness geometry, environment for build/dependency conventions, and other frameworks only when their consumers are admitted.

Trade-offs: specialization removes irrelevant instructions but adds content ownership, version maintenance and selection tests; exact profiles are safer than fuzzy matching but need updates; small assets teach concrete mechanics but can encourage copying; immutable bundles consume history bytes but prevent silent resume drift. Shared-source changes and dynamic loading have larger validation cost and stay outside this scope. Mandatory core guidance stays eager; reducing token counts is secondary to correctness.

Review decisions still needed before implementation: accept this pilot scope; settle byte bounds; select the precise baseline and compatible pytest range; confirm the trusted normalization/serialization seam against current code; choose behavioral thresholds after baseline characterization and an explicit live-run budget. These are concrete implementation/promotion decisions, not reasons to block this documentation draft. PLAN-0064 lists the proposed sequence.

This spec narrows one part of [IDEA-0007](../ideas/IDEA-0007-skills-and-tools-working-interfaces.md). The broader idea remains proposed. References: [package convention](../../agent-packages.md), [evaluation policy](../../evaluation-and-acceptance.md), [authoring contract](SPEC-0028-test-authoring-agent.md), [host eval](SPEC-0044-isolated-agent-evaluation.md), and [Agent Skills resource structure](https://agentskills.io/specification). Portable file organization does not itself implement resource loading or authorize application tools.
