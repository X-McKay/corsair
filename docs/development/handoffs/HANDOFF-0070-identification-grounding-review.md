---
id: HANDOFF-0070
kind: handoff
title: Identification grounding review
status: recorded
updated: 2026-10-13
related: [SPEC-0051, PLAN-0055, SPEC-0024, SPEC-0038, ISSUE-0007]
---

# Identification grounding review

## Verified state

Isolated branch `codex/agent-identification-improvements` from merged PR47 base `6be1b5f55224cbf97dc03a89f8c8a29d79f19df4`. Source and evaluation improvements are bounded to identification; source APIs, prompts/skills, provider settings and frozen corpus remain unchanged. Resolve the final commit with `git log -1 --format=%H -- docs/development/handoffs/HANDOFF-0070-identification-grounding-review.md`; verify git status when resuming.

## Validation and blockers

Focused native checks passed 65/65. Baseline and final candidate scripted 16/16; same-profile live baseline and candidate 16/16 each, zero failures/unknown tools/corrections. Full actual Make guards passed 1009 checks; record/link guards passed 5. Complete commands, identities and telemetry totals are in PLAN-0055. Candidate source/config/corpus/skills manifest verified after execution. Native receipt totals are authoritative where zero-valued Evals metrics were dropped. Prompts/skills remain unchanged; the distinct grounding version identifiers reflect model-visible validation feedback. Raw receipts, messages and provider configuration stay private under `.runs/`. No runtime resources were created; no cleanup is inferred for nonexistent infrastructure. No application code or model-written tests ran on the host. Broader held-out/repository/durable qualification and ISSUE-0007 remain separate.

## Decisions and next steps

Both factories now reject partial/whitespace symbol claims through a shared literal occurrence check. Exact quote evaluation is independent of trusted finalization. Matching is not language-semantic proof: strings/comments can contain a matching name. Root owns PR publication; no push/PR is performed in this lane. Next bounded work is an independent frozen held-out localization corpus with honest semantic and abstention dimensions, plus a host-only repository eval set before repository model qualification.

## Continuation prompt

```text
Read AGENTS.md, README.md, CURRENT.md, SPEC-0051, PLAN-0055 and HANDOFF-0070. Inspect branch/source/evidence and verify the recorded baseline/candidate results. Use development/review skills. Continue independent held-out identification evaluation within existing authorization; preserve frozen exposed cases and failed attempts. Do not connect unqualified repository durable or application runtime stages. Run meaningful host-only checks, record telemetry/unknowns and update records/handoff. Root owns publication of this independent PR.
```

## Current-head review correction

Independent review confirmed that Python regex \w excludes valid Unicode identifier continuation marks: a suffixed combining accent was admitted as an exact target. Literal matches now inspect adjacent characters using Python's identifier-continuation check plus Java/JavaScript $. Negative native stage tests cover combining and spacing marks; exact Unicode spellings and existing punctuation/dollar cases remain supported. This lexical rule remains conservative and is not semantic source proof. Prompt/config identity advanced to grounding-2 (planning config v4). No dataset/held-out changes or live provider calls. Earlier broad review-test attempts were interrupted after they stalled in the restricted worktree; subsequent focused checks and scripted comparisons are recorded below.

Focused Unicode/identifier checks:22 passed; development scripted16/16 versus16/16, `.runs/evals/identification/20261013T100737Z-development-scripted`, unchanged estimated requests/tools/tokens. SPEC-0051 and PLAN-0055 replace this branch's previous colliding identifiers; all tracked references updated. These are new record identities, not changes to the other PR's records.

Final affected identification/repository and documentation/dataset guards:77 passed, one existing event-loop deprecation warning. git diff --check passed. Live candidate rerun and full-suite repeat unrun; prior full-suite source remains separately recorded.

## Conservative cross-language lexical follow-up

Cross-review found Java/JavaScript currency symbols and format characters still accepted as partial-name suffixes. The adjacent-character guard now conservatively includes Unicode Sc and Cf categories together with Python identifier continuations; this covers currency and zero-width joiner/non-joiner suffixes while preserving complete literal spellings. It is intentionally not a parser or declaration/semantic proof. Native negative and complete-spelling checks retain existing dollar and punctuation expectations. Identities advance to grounding-3 (planning config v5). No corpus/held-out, provider or authority changes.

Focused native inline/repository identifier checks:28 passed, one existing deprecation warning. Final scripted development16/16 against16/16 at `.runs/evals/identification/20261013T101223Z-development-scripted`, unchanged estimated requests/tools/tokens.
Full-suite repeat, live provider and runtime checks unrun for this bounded correction; earlier checks remain historical. git diff --check passed.
