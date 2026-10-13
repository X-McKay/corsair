---
id: HANDOFF-0093
kind: handoff
title: Provider review corrections
status: recorded
updated: 2026-10-13
related: [SPEC-0066, PLAN-0072]
---

# Provider review corrections

## Verified state

PR #91 on `codex/provider-ticket-adapters` integrates main `1c6d26a` from head `4c09082`. This handoff accompanies the fix commit; resolve published identity from GitHub. Preserved #95 local response/timeout limits and legacy shim. Provider-specific credential names reject ambient/ticket secrets. Agent ticket inputs omit comments by default; opt-in discussion carries authorship, identifiers, timestamps, formats and unverified-participant labels. Raw HTML remains labeled untrusted data, never rendered. Corpus curation must separately exclude oracle-bearing content, including descriptions.

## Validation and blockers

`UV_CACHE_DIR=/tmp/corsair-provider-uv-cache make test-config`: **1659 passed in 91.05 seconds**. Regressions cover merged local limits, forbidden credential references, discussion opt-in/authorship, GitHub dot segments, Azure edits without revision changes and retry after failed output reservation. Initial restricted targeted run stalled and was interrupted after two tests; the successful full host run supersedes it. Source/test whitespace checks passed. No live inference, authenticated ticket calls, native Temporal or OpenShell qualification ran. Azure double-read consistency is bounded observation, not atomic capture.

## Decisions and next steps

Keep and fix #91 rather than folding provider configuration into corpus work. User's existing fix/publication authorization applies; no merge requested. Three smaller review comments were also addressed (dot segments, Azure comment consistency, failed capture cleanup). The suggested `record-numbers.md` is absent in both worktrees, so no duplicate registry was invented. Existing SPEC/PLAN/handoff files and CURRENT carry identifiers. Wait for exact-head CI and independent review; no live qualification claim follows from mocks.

## Continuation prompt

```text
Read AGENTS.md, CURRENT.md, SPEC-0066, PLAN-0072 and HANDOFF-0093. Verify PR 91 head, main and CI. Preserve per-agent routing, toolset identities and #95 limits together. Review credential separation and the default exclusion of discussion from agent input. Evaluation corpus admission must still remove oracles from all visible content. Run affected checks for any correction and update records. Do not merge or perform live provider/ticket qualification without the relevant authorization and targets.
```
