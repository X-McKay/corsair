---
id: HANDOFF-0066
kind: handoff
title: Isolated per-agent evals and the 32768-token response cap
status: recorded
updated: 2026-10-13
related: [PLAN-0048, SPEC-0044, PLAN-0030, HANDOFF-0048]
---

# Isolated per-agent evals and the 32768-token response cap

## Verified state

`make eval AGENT=<name>` and `make eval-baseline` (PR #47) run each agent's suite on the host and file results under `.runs/evals/<agent>/`. Cap-16384 live baselines from main `96f580e`, unshared model, promoted on RIG0: identification 16/16; planning development 9/12, heldout2 6/12; assessment development 12/51, held_out 5/21; chain 1/5. Truncation at the 16384 cap was the main failure cause (PLAN-0048, "Output cap"). A fresh authoring run on main `6d99d66` was 4/27 clean (5 request-limit, 2 max-tokens, 1 tool-retry failures) and is not promoted.

PR #95 admits 24576 and 32768 response caps and a 300 s timeout in `LocalModelConfig` (defaults 2048 and 60 s unchanged), and gives the planning, authoring and assessment evals deadlines and token ceilings that hold one full-cap response. Composition stage budgets and `evals/fixture_e2e/stage-profiles.json` are unchanged.

## Validation and blockers

Server probe on RIG0, no other model user: `max_model_len` 131072; a 32768-token response finished at the length limit after 234.8 s. `make test-config` 1619 passed after merging main `164a556`; CI green. Update 2026-10-13 17:23Z: the cap-32768 runs for authoring, planning development and assessment development are done and recorded in PLAN-0048; still unrun are assessment held_out (interrupted to free the model for end-to-end runs), planning heldout3 and chain, plus the assessment thinking-budget trial PLAN-0048 proposes. They need the model unshared.

## Decisions and next steps

Al chose to raise the cap before tuning prompts. The cap-32768 runs are new baselines; promote only unshared runs, after comparing them with the cap-16384 reference. If responses still loop to the cap, try a thinking budget (`thinking_token_budget`, already used by the fixture stage profiles) or disabled thinking next. Then PLAN-0048 steps 6 (sandbox replay of authored patches) and 7 (authoring held-out set).

## Continuation prompt

```text
Read AGENTS.md, docs/development/CURRENT.md, PLAN-0048, SPEC-0044 and this handoff. On RIG0, with the model unshared, run the remaining cap-32768 evals listed in PLAN-0048 (do not repeat finished ones) with a provider config setting response_token_limit 32768 and timeout_seconds 300, NOTE="cap 32768, unshared". Compare each with the cap-16384 baseline, promote unshared runs, record aggregates (no held-out case names) in PLAN-0048, update CURRENT.md and write a new handoff. Then tell the #49 thread the model is free.
```
