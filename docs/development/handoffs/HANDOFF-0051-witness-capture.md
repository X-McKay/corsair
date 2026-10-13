---
id: HANDOFF-0051
kind: handoff
title: Execution-node witness capture
status: recorded
updated: 2026-10-13
related: [SPEC-0033, PLAN-0033, SPEC-0027, SPEC-0031, SPEC-0032]
---

# Execution-node witness capture

## Verified state

Branch `claude/witness-capture-mqx96l` from main `0d9bb5a`, draft PR #35; resolve the head commit from git. Delivered offline:

- **Probe.** A repository-owned pytest probe (`nodes/witness_probe.py`; native `sys.monitoring` and audit hooks) is injected by `PytestRunner` in place of `-m pytest`. It is scoped to an operator-approved envelope (target file, symbol and planned effect file name) and to each test's call phase.
- **Read-back.** One fixed command reads the record after a completed execution, with no retry.
- **Mapping.** `nodes/witness.witness_evidence` turns the record into the SPEC-0027 witness and test-phase sandbox events. It refuses on any mismatch of nonce, probe, target, artifact or integrity.
- **Composition.** E2E-0 requests a witness only when the identification target matches `FixtureCase.witness_envelope`. Over the reviewed SPEC-0018 pair the gate now permits `completed`/`reproduced`/`verified`.
- **Qualification state.** Nothing is live-qualified. The probe is tamper-evident, not tamper-proof (it runs in the test interpreter), and the effect is bound by file name only.

## Validation and blockers

- **Offline:** `make test-config` gave 820 passed (781 on main) in the cloud container and on RIG0 at `646f7fd`. CI is green on `646f7fd`.
- **Reviews:** an independent Opus review and Al's review (two P1s) found attribution failures. All are fixed with real subprocess regressions; see PLAN-0033.
- **Live (`make qualify-witness`): not run.**
  - The shared RIG0 kind cluster (built by the live E2E thread on a fresh node; network 3/3, admission 1/1) was handed over.
  - The qualification fixtures require the kubeconfig, owner state and evidence inside the running worktree.
  - Al approved hardlinking the kubeconfig into `/home/al/git/corsair-witness`, but the RIG0 session's auto-mode safety check denied each staging attempt, three in all. Nothing was staged and the cluster was not touched.
  - The exact command sequence to run the gate interactively is in this thread and in PLAN-0033's next action.

## Decisions and next steps

- **Settled:**
  - The in-interpreter operator probe, chosen over a kernel-only observer (decision card, recommended option).
  - Envelope binding until the plan carries a typed effect.
  - The probe travels as an argument, so the image and the SPEC-0032 tree admission are unchanged.
- **Next:** run the live gate on RIG0, either interactively or after the RIG0 session leaves auto mode, then record the four runs, the gate result and cleanup in PLAN-0033 and CURRENT.md.
- **Later:**
  - A typed planned effect path from the planner.
  - A layered out-of-process cross-check.
  - Plugging the witness into the fully live E2E runner factory (PLAN-0034).

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then SPEC-0033, PLAN-0033 and this handoff. Verify PR #35's head and CI. On RIG0, in /home/al/git/corsair-witness at that head, stage the kind state and reused live-e2e evidence as listed in PLAN-0033 (with the owner's approval for the kubeconfig link), run `make qualify-witness` once, then remove the link and reinstall the gateway in corsair-live-e2e. Record the actual per-run witness, gate result and cleanup in PLAN-0033 and CURRENT.md, without rerunning a failure blindly, and write a new handoff.
```
