---
id: HANDOFF-0086
kind: handoff
title: Framework resource spec review revision
status: recorded
updated: 2026-10-13
related: [SPEC-0059, PLAN-0064, HANDOFF-0083]
---

# Framework resource spec review revision

## Verified state

PR70, codex/framework-skill-spec in /tmp/corsair-framework-spec. Started from 95c62a0 and merged main 497db9f. Resolve the revision containing this record with Git. SPEC-0059 and PLAN-0064 remain draft; IDEA-0007 remains proposed. Only documentation changed relative to main. The user authorized incorporating review feedback, not runtime implementation or merging.

The revision uses existing Supported/matrix evidence, defining framework identity from actual fields because rows have no standalone ID. G12 must supply admission evidence to production authoring; explicit operator fixtures can support the isolated pilot. It chooses measured token headroom within 8 KiB resource/16 KiB rendered-bundle ceilings, common frozen budgets and separate exhaustion outcomes. It names the RunContext instruction callback, prompts.py placement, compact durable identity, native serialization check, catalogue/case evaluation identities, and new development/held-out sets with rebaselining. It preserves current plain-assert, witness protection and latest-admitted-write reading rules.

## Validation and blockers

Full offline make test-config passed 1381 checks (one existing SDK warning); final record/link checks passed 5, and diff check is clean. PLAN-0064 retains commands and history. An initial edit invocation failed because bare python was unavailable; reran the edit using the existing Python 3.12 virtualenv. No new resources, prompts, eval data or application code were implemented. No provider, behavioral experiment, sandbox or native replay qualification was run. Temporal can still serialize rendered instructions in model request payloads; compact deps alone do not prove history deduplication.

## Decisions and next steps

Publish the documentation revision to the existing draft PR70 and answer review. Next is acceptance of the bounded spec and implementation scope, followed by the explicit baseline/dataset/headroom/serialization gates in PLAN-0064. Do not rewrite frozen datasets silently, tune on held-out data, increase production budgets, or promote a baseline from this draft. The CURRENT entry is a table row explicitly labeled draft.

## Continuation prompt

```text
Read AGENTS.md, CURRENT.md, SPEC-0059, PLAN-0064 and HANDOFF-0086. Inspect PR70's actual head and review feedback. Preserve the draft versus accepted distinction. Address authorized spec revisions; implement only after the user accepts that scope. Before candidate measurement, pin the baseline and matrix, freeze separate datasets, establish token headroom and verify the native instruction/serialization seam. Record actual checks and remaining limits.
```
