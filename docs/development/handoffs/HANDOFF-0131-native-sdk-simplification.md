---
id: HANDOFF-0131
kind: handoff
title: Native SDK simplification
status: recorded
updated: 2026-10-14
related: [SPEC-0080, PLAN-0095, SPEC-0079, PLAN-0094, ISSUE-0009]
---

# Native SDK simplification

## Verified state

The user accepts keeping the current full agent-package structure while designing around out-of-box PydanticAI. SDK-agnostic exploration is deferred. All seven factories have been simplified for existing PR132; source base is 817a8f8. Resolve the amendment commit through git when this handoff is published. Documentation reflects native `AgentSpec.from_file(...)` at fixed trusted package paths and `Agent.from_spec(...)` with explicit Python model, capabilities, typed contracts/validators, retries and native durability. Remove custom construction/selection helpers and capability_selection metadata. YAML metadata retains config_version/prompt_version; factory_identity is provenance-only file hashing.

## Validation and blockers

Amended-source checks: 13 native/package checks (all seven offer captures), 25 focused consumers and full offline suite2323passed6skipped10warnings48.76seconds. Prior 2329-pass full suite,60targeted,22parity and scripted receipts belong to their earlier frozen source. Seven final live jobs remain unrun/user-deferred; original corrected pre-manifest scores remain4/8environment,8/8identification,1/5planning. ISSUE-0009 and wider runtime/composition admission remain open. Documentation guard initially4passed1failed during concurrent source migration (issue_identification agent.py SyntaxError); the stable full suite above passed the guard. `git diff --check` passed. These are distinct from runtime qualification. Preserve private raw exports and unrelated Open-PR records/CURRENT paragraph.

## Decisions and next steps

Keep owned skill files and eager procedure loading. Native Harness Skills is the intended discovery/disclosure facility; its separate skills-extra dependency is not yet installed or pinned, and integration requires compatibility and activation/budget/validator checks. It does not itself read references or execute scripts. No generic SDK schema, Google adapter, marker protocol or new recorder was implemented. The user specifically identified native Harness Skills/Coder reuse; evaluate the individual upstream capabilities and compatible dependency next, preserving role authority and evidence. Exactly two native probes, independent authors and immutable outcome-blind validity remain unchanged. Update the existing PR under user authorization; no merge authorized. Fresh live baselines remain user-deferred. Scripted amended-source registry checks pass: environment16/16, identification8/8, planning5/5, authors8/8 each, validity7/7, final4/4 and chain5/5. No source change here enables native Skills or Coder; current eager behavior is preserved.

## Continuation prompt

Continue PLAN-0095's accepted native SDK amendment. Verify all seven factories use direct native spec construction and explicit Python capability authority; provenance helpers only hash files. Run meaningful parity/affected checks, record actual results, preserve old-source evidence and user-deferred live status, then update PR132. Do not publish raw .runs or alter unrelated Open-PR material.
