---
id: HANDOFF-0037
kind: handoff
title: PR22 calibration provenance re-review
status: recorded
updated: 2026-10-12
related: [HANDOFF-0035, HANDOFF-0034, PLAN-0018, ISSUE-0007]
---

# PR22 calibration provenance re-review

## Verified state

Local main was clean at `0578521ca06199fb058fe91712f9f517cc0c3132` before this review record. PR22 advanced to `39dbf1150497c84edd72265d03c4b8270b2c7ead`, incorporated that main, and was mergeable with Development guards CI passing. Resolve the commit containing this record from Git.

The updated planner abstention branch, exploratory/confirmation split and branch handoff address the prior design and handoff findings. Individual attempt labels replace case-history calibration truth. One remaining implemented gap: calibration readiness admits an output hash without the producing skill hash, contrary to the stated attempt provenance contract. A direct reproduction returned `skill_sha256=None`, `calibration_ready=True`, and one admitted record. Posted the finding in [the follow-up review](https://github.com/X-McKay/corsair/pull/22#pullrequestreview-5494723439). PR22 remains open; no merge or source edit was performed.

## Validation and blockers

Isolated archive of exact PR head: `PYTHONPATH=src:. timeout 60s /home/al/git/corsair/.venv/bin/python -m pytest tests/configuration tests/unit tests/agents tests/temporal/test_fixture_contracts.py tests/temporal/test_issue_analysis_composition.py -q` passed 369 checks in 6.48s with the existing event-loop deprecation warning. Log and review payload are private under `.runs/pr22-review-update-20261012/`. No inference, Temporal, OpenShell or real-project execution ran. ISSUE-0007 remains blocked, and HANDOFF-0034 remains the runtime/corpus checkpoint.

## Decisions and next steps

The user authorizes merging PR22 if review passes, otherwise posting remaining findings. Require both output and skill identities before admitting a label to calibration, while allowing partial historical records to load; add the missing-skill exclusion check. Re-review the updated PR head and merge if sound. Reconcile this review checkpoint with branch records before merging; do not overwrite either history. No new runtime qualification is established by these offline checks.

## Continuation prompt

```text
Read AGENTS.md, CURRENT.md, PLAN-0018, ISSUE-0007 and this handoff. Inspect git and PR22's latest head rather than assuming this snapshot is current. Use the Corsair review skill to verify calibration admission requires output and skill identity, inspect remaining changes and run proportionate offline checks. Merge if review passes under the user's existing authorization, otherwise comment with concrete findings. Preserve HANDOFF-0034 runtime/corpus limits, update records and leave a new handoff after substantial work.
```
