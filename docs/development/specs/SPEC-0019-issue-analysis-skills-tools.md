---
id: SPEC-0019
kind: spec
title: Issue-analysis procedural skill and restricted tools
status: accepted
updated: 2026-10-12
related: [PLAN-0018, SPEC-0014, SPEC-0016, ISSUE-0007]
---

# Issue-analysis procedural skill and restricted tools

## Goal and scope

The user explicitly requested agent-owned skills and tools to carry procedural detail and guide actual evidence-reading trajectories, prioritizing functional end-to-end behavior over token/latency optimization. Add one issue-analysis procedure and explicit restricted native toolset, preserving the read-only stage and [investigation contract](../../investigation-contract.md). Application execution and the full graph remain separate gates.

## Boundaries and design

The reviewed `skills/analyze-issue/SKILL.md` owns the general inventory/read, operation/exception ordering, attacker/resource/access preconditions, conditional effects, missing facts and citation procedure. It contains no fixture answers, project/API-specific fixes or evaluator labels. The short agent instruction owns stage objective and trust boundaries. Saved task files cannot select, replace or edit the skill.

Use pinned PydanticAI2.55.0 native `Capability` with the exact operator-owned skill text supplied eagerly. This single-purpose stage always needs the same skill; progressive discovery would add no selection benefit. There is no custom skill registry/loader, new dependency, shell or general filesystem capability. Fixed package-file loading occurs before model calls; record its SHA256 and verify actual native wire instructions. This proves delivery, not model adherence. Native Harness Skills was considered but would add an unnecessary dependency and on-demand loading for this mandatory skill.

`tools/source.py` owns the existing immutable saved-input lookup and a native `FunctionToolset`, with stable `issue_analysis_source` identity. Its only function remains `read_source`, limited to listed canonical keys and80 lines. Public factory/dependency imports remain compatible. Scope/current-run read requirements remain. SPEC-0020 subsequently moves quotation ownership to a trusted native output function after validating model-selected references. Native SDK execution and Temporal integration remain the owners of scheduling/durability; no trajectory scheduler is added.

## Acceptance and validation

Check actual native request instructions contain the skill and expose only the admitted tool; preserve key/range/current-run/scope refusals, authority checks and native usage limits. Evaluate actual source-read-before-citation trajectory, missing-source abstention, guarded/hostile contrasts, semantic correctness and budget/usage separately. Skill exposure alone cannot qualify adherence or reasoning. Repeat the original cases and independently frozen ordering contrasts under an explicit functional budget; retain failures and independent actual-output reviews. No larger budget or lexical pass can excuse an incorrect application prediction.

Run affected offline/direct fixture and native same-factory durable qualification where applicable. Historical histories bind the old agent/toolset identity; do not claim new native durable/provider qualification from old results. Preserve source/skill/tool/config/fixture hashes and native messages/receipts. Production dependency-reference intake and application tests are not admitted by saved reference excerpts.

## Decisions and open questions

User authorization covers this implementation and bounded testing. Root owns integration/inference/publication; Sol authored the general skill and independently reviews the native composition. No additional approval gate is introduced. Whether this procedure solves ISSUE-0007 must be determined by actual source-grounded output and independent evidence, not directory layout.

Delivery is currently a source-checkout recipe (`tool.uv.package=false`). The required Markdown file is read before the agent is created; missing content fails rather than silently dropping the procedure. No wheel/package-data or deployed-image inclusion is qualified. Fresh native Temporal tests validate new histories only, not migration/replay of pre-change toolset histories.


The evidence-coordinate continuation clarifies saved-file-local line coordinates in the inventory and native tool descriptions. The procedure separately describes internal effects and returned results and requires illustrative values to follow the supplied operations. Native output correction names the rejected reference and already-read local ranges; it never translates, clamps, rereads or repairs an invalid reference. These are general communication improvements prompted by observed evidence errors, not case-specific analysis logic. A numbered-return DTO or more powerful tool is deferred because the same admitted data suffices.
