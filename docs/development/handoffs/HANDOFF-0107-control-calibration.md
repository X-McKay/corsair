---
id: HANDOFF-0107
kind: handoff
title: Control calibration and the routes to a negative verdict
status: recorded
updated: 2026-10-13
related: [PLAN-0084, SPEC-0040, SPEC-0027, SPEC-0033]
---

# Control calibration and the routes to a negative verdict

## Verified state

Branch off main `5890a31` (PR #115 merged). Delivered: [PLAN-0084](../plans/PLAN-0084-control-calibration.md), the SPEC-0040 control calibration. A plan whose safe behavior is `no_file_open` can now reach `not_reproduced` on the reported revision when the run's control open is recorded; without that it is refused and the gates stay `inconclusive`. Offline only.

How LIKELY_NOT_EXPLOITABLE is reached, read from `core/disposition.py` (`_assess_run`, `assess`, `admit`), `nodes/witness.py` and `composition/direct.py`. The label needs `not_reproduced`, which needs every baseline run classified `safe`: delivery and completion observed, no execution failure, the frozen patch, exactly the planned two tests with one outcome each and none skipped or errored, no test-phase sandbox event on the witness path, the control passed, the security test passed, and an admitted witness with the target entered, the planned effect absent and the plan's safe behavior. With a candidate run, fix is `not_verified` (limitation `baseline_not_reproduced`); `not_applicable` only without one.

Routes to a negative verdict:

| Route | Before | After this change |
|---|---|---|
| Baseline raises the plan's named exception without the planned open | open | open (unchanged) |
| Baseline never makes the planned open (`no_file_open`) | closed: absence counted on the candidate only | open when the control calibrates it |
| `refuted_in_scope` | closed: `admit()` always rejects it | closed, out of scope here |
| No fix revision (single-revision run) | closed: `investigation/build.py` refuses it | closed; Al chose "Allow fix-free runs" (18:3xZ), Node thread owns the change |

Witness coverage limit: the only Python recorder is `audit_open` (file opens), and the probe records no other effect kind. Negatives for SSRF, command injection, SQL, deserialization and other non-file effects stay `inconclusive` whatever the code does, and so do their positives.

## Validation and blockers

- `PYTHONPATH=src:. .venv/bin/python -m pytest -q tests/unit/test_witness.py tests/agents/test_fixture_composition.py tests/configuration`: 293 passed (70 witness and composition tests), after fixing the new records' status and heading.
- `make test-config` on main 5890a31 plus this change: 1847 passed, with one records-format failure fixed and re-checked above.
- Not run: any live model stage; the OpenShell route; the evidence-assessment dataset (probe bytes unchanged, so its digests stand; `witness_evidence` callers there pass no absence plan).
- Limit: calibration shows the probe records the target's opens in this run, not that the security payload aimed at the sentinel; a payload resolving to another file name still reads as absent.

## Decisions and next steps

- Calibration guards absences only (PLAN-0084 decision, recorded in SPEC-0040).
- Next: merge with #113's Docker route and #109's recorder-built request (SPEC-0073 changes `witness_request`; this change touches only `witness_of`), then run the not-exploitable fixture live with a `no_file_open` plan; fix-free runs (Node thread); a `refuted_in_scope` admission rule needs its own spec.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then SPEC-0040, PLAN-0084 and this handoff. Verify the calibration in src/corsair/nodes/witness.py and composition/direct.py against main. Next bounded action: after #113 and #109 merge, run the not-exploitable fixture on the Docker route live and record whether the planner chooses no_file_open or an exception, and the admitted triple. Do not change the gates, stage order, witness requirement or matrix rows. Run make test-config, update records and write a new handoff.
```
