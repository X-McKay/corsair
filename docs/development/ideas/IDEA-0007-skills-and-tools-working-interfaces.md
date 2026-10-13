---
id: IDEA-0007
kind: idea
title: Revisit skills and tools as working interfaces, not just delivered instructions
status: proposed
updated: 2026-10-13
related: [IDEA-0006, SPEC-0023, SPEC-0044, SPEC-0052, PLAN-0056]
---

# Revisit skills and tools as working interfaces, not just delivered instructions

## Problem and evidence

Corsair can improve its agents by treating skills and tools as a working interface: the skill teaches a useful method, the tools make that method practical, and trusted code enforces its boundaries. Checking that skill text reached the model is necessary, but it does not tell us whether the procedure was appropriate, applied correctly, or useful.

The user requested that this follow-up to the agent/evaluation review be recorded for review and consideration. This idea is based on main `0ad9900c3bfd9a44fb3e5c4b3e4422313163dff8`. It proposes changes; it does not implement new skills, tools, evaluators or runtime authority.

### Existing strengths and concrete opportunities

The inspected planning, authoring and environment skills contain valuable procedural knowledge. Planning explains scratch-root geometry and the limits of effect witnesses; authoring explains assertion direction and bounded corrections; environment explains recipe discovery and failure attribution. Their native factories already combine trusted instructions, restricted tools and output admission. The opportunity is to improve this design, not replace it.[1] [2] [3]

Several details motivate a joint skill-and-tool improvement:

- **Skills carry dense procedures without supporting resources.** The inspected stage skills are compact, numbered instruction lists. Some objective and authority statements repeat factory instructions and validators. Critical reminders can be useful, but their canonical ownership should be clear. Adding prose should not be the default fix for an awkward interface.
- **Source navigation requires avoidable inference.** Window reads already compute end lines and return numbered evidence; repository mode adds bounded list/search/read and repeated-read notices. Explicit continuation and coverage facts could help agents avoid unnecessary exploration without treating every extra read as wrong.[4] [5]
- **Planning can overconstrain investigation.** Its skill says to stop reading after the target and baseline are read. That fits curated cases but can exclude a legitimate helper/call-chain dependency. Any broader procedure must remain within the available source inventory and current authority; whole-repository tools are not yet adopted by planning.[1]
- **Authoring needs clearer feedback and witness ownership.** Its run tool binds observations to a patch, while the skill describes correction and witness obligations. Static/simulated host observations must not imply actual test execution. Assertions about planned behavior must also be distinguished from installing instrumentation. The recorded live author-created audit-hook failures make this more than a stylistic concern.[2] [6]
- **Environment instructions and arguments can be clearer.** The skill classifies recipe steps as `dependency` or `build`, but `run_setup_command` accepts only `command`. Clarify that recipe classification is distinct from a command argument, or add a typed phase input only if execution actually uses it.[3] [7]

### Build on accepted and ongoing work

[IDEA-0006](IDEA-0006-agent-package-convention-and-scaffolding.md) has been accepted with changes. Main now includes the environment reference package: `prompts.py`, `dependencies.py`, `validation.py`, one module per tool and explicit registration. The [canonical package convention](../../agent-packages.md) uses `toolset_sha256` in the existing evaluation identity; a separate manifest/receipt layer and generator are deferred. This idea preserves those decisions and addresses the quality of the interfaces within that layout.

At this base, [PR #49](https://github.com/X-McKay/corsair/pull/49) proposes authoring witness/admission and budget changes, [PR #44](https://github.com/X-McKay/corsair/pull/44) changes planned witnesses, and [PR #63](https://github.com/X-McKay/corsair/pull/63) proposes actionable setup blockers and stopping behavior. Their proposals are not current-main behavior. Reconcile their latest state before implementing overlapping feedback, examples or tests; do not recreate those mechanisms in another skill layer.

## Proposal and limits

### 1. Give instructions, skills, tools and enforcement distinct jobs

**Agent instructions** hold the stable objective, trust boundary, permitted outcomes and reference to the procedure. Keep them concise and always available. Mandatory constraints must not depend on successful optional skill discovery.

**Skills** teach the method: applicability, prerequisites, decision points, relevant tool use, examples, expected evidence and stopping conditions. They should explain how to recognize the next useful action—and when not to take it—rather than become a growing catalogue of prohibitions.

**Tools** perform bounded operations and return usable observations. Names, argument descriptions, result fields, truncation and errors are part of the model-facing interface. The skill and actual offered schema must agree.

**Trusted contracts, ports and admission code** enforce approved paths, budgets, source/patch identity, current-run provenance and security dispositions. Skill activation never grants authority. No procedure can convert an unknown execution, failed control or sandbox refusal into application safety.

For example, citation coordinates are enforced by contracts/admission; the reader explains its returned coordinates; the skill explains when source evidence is needed. Maintain a short reminder in the procedure where it helps, rather than three independently maintained long explanations. Do not remove critical guidance merely to reduce token counts.

### 2. Keep the core procedure eager; add optional resources when justified

The present mandatory stage procedures are usually appropriate for eager loading. A useful evolution is an always-on core with focused resources for particular task or technology needs—not deferring the entire stage or inventing dozens of tiny skills.

An illustrative planning package is:

```text
skills/
  plan-two-tests/
    SKILL.md                         # Core method and decision points
    references/
      filesystem-scope.md             # Roots, fixture geometry and path effects
      native-test-conventions.md      # Infer conventions from actual saved tests
      witness-boundaries.md           # Limits of admitted observations
    assets/
      example-plan.json               # Synthetic worked example, not an eval oracle
```

These supporting files are proposed, not present on the reviewed base. Create one only when a concrete failure class demonstrates its value. If every run needs a reference, select it deterministically or move its essential guidance into the core. Avoid deeply nested reference chains and duplicated procedures.

The [Agent Skills specification](https://agentskills.io/specification) provides a compatible resource structure and progressive disclosure pattern. Use descriptive applicability and non-applicability: filesystem fixture guidance is relevant to path geometry, not automatically to every security concern. Examples must respect actual runtime/framework evidence instead of treating pytest or Maven snippets as universally valid.[8]

Keep evaluation cases, vulnerable/fixed labels and held-out answers outside skill resources. Examples explain mechanisms without copying benchmark answers. Optional scripts do not imply execution authority; deterministic helpers should generally remain normal, tested application/developer code rather than a second implementation hidden in skill folders. No arbitrary host execution is added.

Application skills under `src/corsair/agents/` and Claude/Codex development skills are different consumers. Reuse the portable format where helpful, but keep their procedures and access separate. The existing scaffold skill guides repository development; application skills do not acquire its filesystem or shell privileges.

### 3. Use native loading, with explicit authority and identity

The pinned PydanticAI 2.55.0 `Capability` accepts `id`, `description` and `defer_loading=True`; a deferred bundle can be activated with native `load_capability`. This is an option to test, not grounds to install another skill framework.[9]

Compare three approaches for a genuinely optional procedure:

1. Eagerly include it with the core.
2. Select it deterministically from trusted task/environment data.
3. Advertise its metadata and let the model load it when applicable.

Prefer the simplest approach that works. Native guidance advises against deferred loading when the capability is used on most turns: the discovery round trip can cost more than it saves. Corsair's small, mandatory skills need not change loading mode.[10]

Start with instruction/reference-only supplements. If a selected bundle contributes tools later, availability must remain bounded by the stage's operator-authorized surface and current run state. Loading a bundle cannot restore a withdrawn tool, increase a budget or authorize a retry after unknown delivery. `allowed-tools` metadata is not an enforcement mechanism.

Use a narrow catalogue of repository-owned, trusted resources. Never discover executable procedures from the untrusted repository under investigation. Resource retrieval, if needed, must be bounded and confined to that catalogue—not an unrestricted file reader.

Preserve stable native capability/toolset identities. Record the actual requested/delivered resource identities and bytes in existing private observations where feasible; the core skill digest alone does not identify an optional reference's bytes. Do not introduce a cross-mode receipt framework as a prerequisite. Deferred loading is not qualified merely because the constructor supports it: verify affected direct/resumed/durable behavior, provider requests and Temporal replay before adoption.

### 4. Make tools carry more of the practical work

Keep the accepted `tools/<tool_name>.py` convention and explicit registration. One file per tool is an ownership rule, **not** a requirement to expose every internal function as a separate model tool. A coherent domain operation may use several internal helpers while preserving a clear effect and evidence boundary.

Anthropic's tool-design guidance favors a few distinct workflow-oriented tools, useful context, bounded results and descriptions that make inputs/outputs unambiguous. Apply these as hypotheses to evaluate, not a reason to merge unrelated privileged operations or remove provenance.[11]

#### Source navigation

Improve existing results before adding new tools. Useful facts may include the actual range, EOF, truncation, valid continuation and already-returned coverage. Have trusted code derive those facts; the model should not reconstruct them from instructions or manufacture citation authority.

Permit additional source reads when a concrete uncertainty warrants them within the admitted inventory. Measure repeated no-information actions and unrelated exploration separately. A direct read can be valid without search when the supplied target is sufficient; search hits still do not authorize citations.

A later `read_symbol` or bounded context-bundle tool may help if it returns attributable source ranges and handles ambiguous symbols conservatively. It needs language/alias/overload cases before adoption. Do not replace evidence with a generated summary or silently expand planning to whole-repository access.

#### Authoring observations and correction

Keep the existing write digest/size, patch-bound run identity and withheld security outcome. Make execution mode, final-patch coverage, observed failure category and permissible next action clearer where existing feedback leaves ambiguity.

A collection error may permit an approved test correction. A workspace refusal or uncertain delivery does not become repairable by rewriting tests. Guidance about correction is derived from trusted state; it cannot expand authority. Suppressed same-response duplicate runs, later independent attempts and final patch/run consistency retain their actual semantics rather than being replaced by a generic retry loop.

Separate ordinary assertions about the planned safe behavior from trusted witness collection. The author must not install audit/monitoring hooks to replace the operator-owned witness. Coordinate wording, examples and negative cases with PR #49 and the actual admitted facility; do not imply that all witness types are interchangeable.

Host authoring evaluation remains static/non-executing. A model-facing description should not imply that a simulated observation proves imports, control success or test polarity. Actual execution dimensions require replay of frozen authored bytes through the admitted sandbox path, with no new model call changing the patch.

#### Environment setup and errors

Clarify command arguments versus recipe phase classification. Preserve delivery/completion, failure layer and retained output references as separate facts. Ordinary build feedback, a policy denial and unknown delivery do not offer the same correction path; actionable errors must never mean “try again regardless.”

Prefer small domain-specific result improvements over a universal `{status, data, error}` envelope. Source windows, writes and execution observations still need distinct contracts. A common reason vocabulary can improve diagnostics without forcing identical error handling or retry semantics across agents. Coordinate with PR #63 before adding another blocker/stop taxonomy.

MCP's input/output schemas and structured results provide useful interoperability guidance if tools are later exported. Current in-process tools need not become MCP services. Tool annotations are hints, not runtime enforcement.[12]

### 5. Measure usefulness, not loading frequency

Retain the distinction between configuration and behavior, but broaden the questions to:

> Available → selected when applicable → delivered → applied correctly → useful outcome.

For current eager stage skills, selection is deterministic—not a model discovery action. Verify delivery and evaluate the resulting behavior. For optional procedures, add trigger-positive, trigger-negative and boundary cases to measure warranted selection and unnecessary activation separately. Successful loading is not task success; a load may be unnecessary when adequate guidance was already provided.

Use the existing [evaluation and acceptance policy](../../evaluation-and-acceptance.md), [SPEC-0023](../specs/SPEC-0023-native-skill-evaluation-protocol.md) and [isolated loop](../specs/SPEC-0044-isolated-agent-evaluation.md). Add named observable dimensions rather than a composite “skill score”:

- Correct grounded outcomes and warranted versus unnecessary abstention.
- Tool argument errors, required evidence omissions and stale patch/run pairings.
- Repeated no-information actions and inappropriate correction attempts.
- Requested/delivered resource identity, behavioral evidence coverage and selection applicability.
- Covered timing, requests, tokens and returned bytes alongside correctness.

Missing request, message, receipt or trace evidence stays unknown/unscorable, not pass or proof that no action occurred. Allow valid alternative trajectories; require ordering only where a real dependency warrants it. Do not claim access to the model's private comprehension.

Compare one coherent treatment at a time against a frozen baseline: procedure/example wording, description, structured feedback, or loading strategy. Keep cases, evaluator, model/profile, authority, other budgets and execution mode fixed; record any unavoidable drift. For a joint skill/interface treatment, attribute the measured benefit to the bundle unless separate ablations identify the contribution. A changed toolset hash should identify the declared treatment, not automatically invalidate all comparisons.

Test optional guidance ablations only in isolated configurations; mandatory policy and deterministic gates stay intact. An unchanged finite-suite result may mean a resource is redundant or that the suite does not exercise its value. Do not conclude universally that the model needs no skill.

Scripted native `TestModel`/`FunctionModel` fixtures test request construction, schemas, delivery and evaluator sensitivity. They do not establish how a live model responds to improved instructions. Use controlled live measurements for behavioral claims, and separate admitted sandbox replay for execution claims. Retain all repeats and failed candidates, protect held-out cases, and never automatically promote a baseline.

### 6. Start with an authoring correction-and-finalization pilot

This workflow has a focused objective, existing tool interfaces, patch identity and concrete failures. The first experiment need not add a loader, new tools or a resource catalogue.

1. **Reconcile the base.** Verify PR #49 and other relevant changes, preserve the accepted package convention, and select the authoring implementation to measure. Do not mix a structural migration and a behavior experiment into an unattributable change.
2. **Freeze development cases and expectations.** Include a valid first patch, an approved collection-error correction, workspace refusal, exhausted budget, stale final patch and injected instructions asking for unauthorized instrumentation. Preserve two-test/witness admission. Add valid-alternative and good/bad/coverage-loss controls for new evaluators.
3. **Establish a baseline.** Record native configuration, skill/toolset identity, all attempts and coverage. Derive behavioral regression thresholds from the baseline and freeze them before testing a candidate. Tiny suites do not establish population reliability or tail latency.
4. **Test one targeted improvement.** Clarify observation mode, witness ownership, admissible correction and final patch/run consistency. Prefer existing feedback fields unless a concrete ambiguity needs a small typed addition. Measure live-model behavior when authorized; host fixtures remain non-execution evidence.
5. **Add modular guidance only if it helps.** Extract one focused framework-specific reference if a recurring failure demonstrates its value. Compare explicit selection with eager or native deferred loading; qualify affected consumers/replay paths before integration.

A candidate is useful when it improves the selected failure class without a preregistered correctness, authority, grounding, abstention or coverage regression. Insufficient evidence means inconclusive, not successful. Any claimed two-test execution improvement still needs admitted replay of the exact frozen bytes.

### Exclusions and complexity limits

This idea does not add an agent coordinator, alter the fixed graph, install developer skills, widen runtime access, change two-test/disposition semantics, execute authored code on the host or weaken policy to obtain a pass. It does not mandate a generator, base class, plugin registry, shared conversation memory, tracing service or new manifest/receipt layer. Shared code still needs a demonstrated second consumer.

## Decision

**Proposed for review and consideration.** The user requested a polished idea PR, not implementation or acceptance of the design. Keep the accepted architecture and IDEA-0006 decisions authoritative.

Recommended direction: improve the procedures and agent-facing tool results first; introduce modular loading only where measurements show a benefit. If selected, write a narrow spec/plan for the authoring pilot after reconciling overlapping PRs. Set its baseline, treatment, acceptance dimensions and mode limits before editing runtime skills or tools. Broader agent migration, optional resource retrieval and durable loading remain separate follow-ups.

## References

[1]: https://github.com/X-McKay/corsair/blob/0ad9900c3bfd9a44fb3e5c4b3e4422313163dff8/src/corsair/agents/test_planning/skills/plan-two-tests/SKILL.md "Corsair planning procedure, witness reasoning and source-read guidance"

[2]: https://github.com/X-McKay/corsair/blob/0ad9900c3bfd9a44fb3e5c4b3e4422313163dff8/src/corsair/agents/test_authoring/skills/write-native-tests/SKILL.md "Corsair authoring procedure and bounded correction"

[3]: https://github.com/X-McKay/corsair/blob/0ad9900c3bfd9a44fb3e5c4b3e4422313163dff8/src/corsair/agents/environment/skills/prepare-environment/SKILL.md "Corsair environment recipe procedure and phase classification"

[4]: https://github.com/X-McKay/corsair/blob/0ad9900c3bfd9a44fb3e5c4b3e4422313163dff8/src/corsair/agents/source/tools.py#L72-L94 "Corsair bounded window reader and numbered evidence"

[5]: https://github.com/X-McKay/corsair/blob/0ad9900c3bfd9a44fb3e5c4b3e4422313163dff8/src/corsair/agents/source/repository_tools.py#L59-L125 "Corsair repository navigation, duplicate reads and budgets"

[6]: https://github.com/X-McKay/corsair/blob/0ad9900c3bfd9a44fb3e5c4b3e4422313163dff8/docs/development/plans/PLAN-0039-live-witness-and-full-chain.md "Recorded live authoring witness failures and chain limits"

[7]: https://github.com/X-McKay/corsair/blob/0ad9900c3bfd9a44fb3e5c4b3e4422313163dff8/src/corsair/agents/environment/tools/run_setup_command.py#L42-L70 "Current command-only setup tool and delivery/completion observations"

[8]: https://agentskills.io/specification "Agent Skills specification: metadata, procedures and progressive resources"

[9]: https://github.com/pydantic/pydantic-ai/blob/v2.55.0/pydantic_ai_slim/pydantic_ai/capabilities/capability.py#L69-L115 "Pinned PydanticAI capability constructor and deferred loading"

[10]: https://pydantic.dev/docs/ai/capabilities/on-demand/ "Native on-demand capabilities and when eager loading is preferable"

[11]: https://www.anthropic.com/engineering/writing-tools-for-agents "Workflow-oriented tool design, result context and evaluations"

[12]: https://modelcontextprotocol.io/specification/2025-06-18/server/tools "MCP tool schemas, structured output and annotation trust"
