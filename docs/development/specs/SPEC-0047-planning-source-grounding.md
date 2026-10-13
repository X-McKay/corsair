---
id: SPEC-0047
kind: spec
title: Planning target source grounding
status: accepted
updated: 2026-10-13
related: [SPEC-0022, PLAN-0051, HANDOFF-0071]
---

# Planning target source grounding

## Goal and scope

Tighten the read-only planner's trusted output admission: a ready plan must ground both tests in the source anchor supplied by the admitted identification. This implements the authorized per-agent improvement review after PR47, independently of the pending typed-witness work in PR44. Existing investigation and evaluation contracts remain authoritative.

## Boundaries and design

The native output function still attaches quotations only from successful current-run reads. Additionally, each test's source references must collectively cover the identification's target path and inclusive line interval. Adjacent and overlapping references are allowed; a gap is refused. References to a baseline test alone cannot authorize an application test plan. Implementation calls must mention the exact supplied symbol at word boundaries, so a different identifier containing that symbol is refused. This lexical check cannot prove a real call or its semantics.

Use native ModelRetry under the unchanged operator correction budget. No new tools, SDK wrapper, execution mode or output schema is introduced. The model-visible correction text changes the prompt identity to test-planning-v6-grounding-1; trusted admission changes config identity to test-planning-config-v3. Other instructions, skill, budgets and provider wiring stay at their existing identities.

## Acceptance and validation

Both valid fixture plans and unsupported branches continue to work. Native FunctionModel tests refuse baseline-only citations, same-file citations outside the target anchor, and symbol substrings for each relevant boundary; a positive adjacent-range case prevents over-restricting citations to one range. Compare frozen development scripted evaluations before/after. Run affected tests and make test-config. Live comparison and durable integration require separate evidence and remain unrun in this workstream.

## Decisions and open questions

Do not duplicate pending PR44 no-baseline refusal or typed witness changes. Reconcile prompt/config identities when those changes are merged. No held-out answers are used to design this guard; the authority comes from the identification input and existing grounding requirements.

Review correction: identifier continuations now include Unicode combining/spacing marks through an adjacent-character identifier check, plus $. Literal occurrence remains a structural boundary check. Existing corpus and tool authority are unchanged.
