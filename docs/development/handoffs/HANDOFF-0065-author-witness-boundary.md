---
id: HANDOFF-0065
kind: handoff
title: Authored tests out of the witness and per-stage tool budgets
status: recorded
updated: 2026-10-13
related: [PLAN-0047, SPEC-0043, PLAN-0039, SPEC-0033, HANDOFF-0057]
---

# Authored tests out of the witness and per-stage tool budgets

## Verified state

Branch `claude/author-witness-boundary-el02vx` (#49), head after merging main `759b016`. The PR does three things:

- **Authoring.** Authoring runs `test-authoring-v7` with config-v3. A deterministic AST admission check (`agents/test_authoring/admission.py`) refuses the following in authored tests:
  - audit hooks, monitoring, tracing and forged audit events;
  - patches of observed facilities, including through the target module's references, keyword and string targets, and `sys.modules` mutators;
  - computed-name access (`getattr`, `vars`, `eval`, `exec`, `compile`, `__import__`, `importlib`, `attrgetter`, `methodcaller`).

  The check gives one typed `RefusedWrite` correction, then the stage ends blocked at `admission`. The reviewed SPEC-0018 bytes are admitted by digest. `read_source` serves the author's own writes and returns a typed `UnreadSource` for absent paths and past-end starts.
- **Stage budgets.** Per-stage caps are derived from the stage input, under operator ceilings. They are recorded per attempt and enforced by native `PrepareTools` withdrawal. Typed `BudgetExhausted` is raised only on native `UsageLimitExceeded` or `TimeoutError`, in both direct and durable modes.
- **Assessment.** The evidence-assessment config is v2, with `tool_budget()` in #64's package layout.

Combined identities with #52/#54:

| Stage | Prompt | Config |
| --- | --- | --- |
| Identification | `issue-identification-v3-grounding-3` | `issue-identification-config-v4-grounding-3` |
| Repository identification | `issue-identification-repository-v1-grounding-3` | `issue-identification-repository-config-v3-grounding-3` |
| Planning | `test-planning-v6-grounding-3` | `test-planning-config-v6` |

## Validation and blockers

Cloud container checks on the merged head (87b8e20):
- **Offline checks (`make test-config`):** 1331 passed.
- **Native Temporal:** 47 passed against the pinned 1.9.1 dev server.
- **Scripted `make eval`:** identification 16/16, planning 12/12, authoring 18/18, assessment 51/51, chain 5/5.
- **CI:** green.

All of these are scripted or offline.

Unrun, deferred by the owner, who asked at 2026-10-13 12:16Z to merge without them:
- the three-run fully live chain with the witness and stage profiles on RIG0;
- live isolated baselines for every changed agent version.

The only live data is a host-only authoring A/B on RIG0, which is indicative only because v5 shared the model. It is in PLAN-0047. No refusal fired live, so the live refusal rate and the token use against the derived caps are unknown.

## Decisions and next steps

- The owner merged without the live run. The before/after comparison against PLAN-0039 is still owed.
- The next step is a follow-up run from a worktree under `/home/al/git/corsair/.worktrees/<name>`, at a frozen main commit containing #49. It needs:
  - the cluster, under the cluster-holder rules;
  - the model server, used by one inference user at a time.
- Evidence goes under that worktree's `.runs` and is archived to `corsair/.runs` before the worktree is deleted.
- #44 rebases over this merge.

## Continuation prompt

```text
Read AGENTS.md, docs/development/CURRENT.md, SPEC-0043, PLAN-0047 and this handoff. On a worktree under /home/al/git/corsair/.worktrees/ at a recorded main commit containing #49, once you hold the kind cluster and the model server, build the cluster (make tools kind-up admission-artifacts admission-install, qualify-admission, openshell-install, toolchain-images-load, qualify-network), then run make qualify-fixture-e2e with CORSAIR_E2E_RUNS=3, CORSAIR_STAGE_PROFILES=evals/fixture_e2e/stage-profiles.json and the RIG0 provider config, evidence under the worktree's .runs. Stop on the first failure, no retries. Compare with PLAN-0039 (authoring audit hooks, cap exhaustion per stage, admitted live verdicts), record refusal counts and token use against derived caps, then run live make eval baselines for the changed agent versions one at a time. Update PLAN-0047's follow-up note, CURRENT.md and write a new handoff.
```
