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

## Gap list (project numbering)

| Gap | Seen in | Cause | Fix in this branch |
| --- | --- | --- | --- |
| 6 | Live run 2 | Security test re-read the unchanged outside file, so it passed on the vulnerable baseline and failed on the fix's `ValueError` | Gate codes `security_passed_with_effect` / `security_failed_with_safe_witness`; authoring skill v9 asserts on what the call returned, catches around the call under absence plans |
| 6b | Docker live-005 | Bare call in an absence-plan test, so the fix's rejection failed it | Same skill rule, stated for any assertion (path, URL, content) |
| 7 | Live run 2 | Probe counted the test's own post-call read as an off-stack open, so the effect was `unknown` and the gate said `witness_missing` (not a `..` normalization issue) | Probe records the test function's direct reads as `body_planned`, never the effect; helpers/event loop/app callbacks stay off-stack |
| 8 | Live run 2, Docker live-002 | Assessment proposed `not_reproduced` where the gate allowed `inconclusive` (gate rejected it; reported verdict was right) | Assessment skill v6 states what `not_reproduced` needs; gate unchanged |
| 9 | Docker live-002 | Security test raised `FileNotFoundError` in its own setup on both revisions; acceptance refused only setup errors and skips | `run_tests` shows a security failure of an unplanned type; finalization refuses the patch with type and line |
| 10 | Docker live-006, corpus rerun pathtraversal-2 | Authoring: prose before bare JSON spent the one correction, then a hidden wrong-line refusal. Planning: about 9k characters of reasoning and no text spent it, then the fenced plan failed the contract (empty `limitations`), hidden behind "Exceeded maximum output retries" | Native `after_model_request` hook on every chain stage: one complete object kept (bare or fenced, prose either side, dropped text recorded), two refused, reasoning-only refused as `no output after N characters of reasoning`; the stop reason lists every correction and the final refusal |
| 11 | Docker live-006, live-002 | Dev run withholds the security outcome, so a test that cannot fail is frozen unseen | Authoring's development runs capture the witness (envelope carried in `TestAuthoringInput.witness`, direct and durable); a security pass while the witness observed the planned effect is shown and refused. Refusing any pass on the reported revision was rejected: it assumes the baseline is vulnerable and makes `not_reproduced` impossible. Live-002's setup error is gap 9 |

## Validation and blockers

`make test-config` 1863 passed on the head with main merged. Scripted evals before/after in PLAN-0082 (all clean). The host replay `tests/unit/test_security_test_distinguishes.py` reproduces run 2's gate outcome with the new codes and shows the absence-plan test shape reaching `reproduced`/`verified`. Not run: live evals, live chain run, `make qualify-witness`.

## Decisions and next steps

The gate stays authoritative; the assessment agent moves. Draft PR #117. Open for Al: whether a reasoning-only answer gets its own correction apart from the format correction (today both share the one; PLAN-0082 has the option). Found by replaying the corpus rerun's planning record offline: the environment stage approved the directory `tests` as a test path, which the planner contract refuses once its other refusal is fixed; that belongs to the environment stage (#120 thread). Next: a live end-to-end run of the fixture case on this branch, then live `make eval AGENT=authoring` and `AGENT=assessment` baselines when the model is free, and `make qualify-witness` at the next milestone gate.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then PLAN-0082 and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. Run the next live fixture end-to-end run on this branch and compare its gate limitations with run 2. Stop claiming the probe qualified until make qualify-witness passes on its digest. Run relevant checks, preserve evidence, update CURRENT.md, and write a new handoff.
```
