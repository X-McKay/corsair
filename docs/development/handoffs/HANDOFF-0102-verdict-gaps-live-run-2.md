---
id: HANDOFF-0102
kind: handoff
title: Verdict gaps from live run 2
status: recorded
updated: 2026-10-13
related: [PLAN-0082, SPEC-0027, SPEC-0033, SPEC-0040]
---

# Verdict gaps from live run 2

## Verified state

Branch `claude/verdict-gaps-run2-n9lj9y` from main 184e609. Implements [PLAN-0082](../plans/PLAN-0082-verdict-gaps-live-run-2.md): test-body reads attributed in the witness probe, two gate codes for a security test that cannot distinguish the revisions, authoring skill v9 and assessment skill v6, and authoring acceptance refusing a security test that errors before its planned assertion (gap 9 from Docker run live-002). Probe digest changed and is unqualified; prompts changed and have no live baseline.

## Validation and blockers

`make test-config` 1797 passed. Scripted evals before/after in PLAN-0082 (all clean). The host replay `tests/unit/test_security_test_distinguishes.py` reproduces run 2's gate outcome with the new codes and shows the absence-plan test shape reaching `reproduced`/`verified`. Not run: live evals, live chain run, `make qualify-witness`.

## Decisions and next steps

The gate stays authoritative; the assessment agent moves. Next: a live end-to-end run of the fixture case on this branch, then live `make eval AGENT=authoring` and `AGENT=assessment` baselines when the model is free, and `make qualify-witness` at the next milestone gate.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then PLAN-0082 and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. Run the next live fixture end-to-end run on this branch and compare its gate limitations with run 2. Stop claiming the probe qualified until make qualify-witness passes on its digest. Run relevant checks, preserve evidence, update CURRENT.md, and write a new handoff.
```
