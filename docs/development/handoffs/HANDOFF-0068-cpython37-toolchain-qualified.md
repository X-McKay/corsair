---
id: HANDOFF-0068
kind: handoff
title: CPython 3.7 toolchain image qualified
status: recorded
updated: 2026-10-13
related: [SPEC-0046, PLAN-0050, SPEC-0033, SPEC-0042, HANDOFF-0067]
---

# CPython 3.7 toolchain image qualified

## Verified state

Branch `claude/toolchain-python37-drklks`, restarted from main bb4f3b7 after #55 (image, runner, parser and probe), #86 (3.7 `__file__` gate fix) and #88 (two-test case patch) merged. This branch carries only evidence:
- The matrix image row `cpython-3.7-pytest` after the 3.12 row.
- A pytest framework row `==6.0.2 || ==6.2.5 || ==7.0.1 || ==7.2.0 || ==7.4.4` scoped to it.
- Unit tests that select it for `>=3.7,<3.12` and keep `>=3.8,<3.12` unsupported.
- The report section, PLAN-0050 (complete), SPEC-0046 (accepted), SPEC-0033, and CURRENT.md.

Live on RIG0 (details and identities in [the toolchain report](../../qualification/openshell-toolchains.md#spec-0046-cpython-37-image-real-case-and-witness-v2-probe-2026-10-13)):
- Toolchain gate passed at 794a003.
- CVE-2021-32839 passed at both commits at 4117e3f, with the witness refused by name.
- `make qualify-witness` passed at 4117e3f, qualifying the `corsair-witness-v2` probe c89e0d65….
- The scripted assessment development baseline was promoted at 51/51.

Remaining limits:
- pytest below 6.0 is not supported.
- There is no witness observation on 3.7.
- Dependency setup for real 3.7 cases is not covered.
- pytest 6.0.2 to 7.2.0 rest on real output checked offline, not on sandbox runs.
- The SPEC-0042 report is not regenerated. Stored requirements reselect 15 revisions of 9 Python cases onto the new row.

## Validation and blockers

The RIG0 commands, three failed attempts and their corrections are in PLAN-0050. Evidence lives under the worktree's `.runs/` and in the archive `/home/al/git/corsair/.runs/py37-toolchain-20261013/` (1363 files). Archive anything newer before deleting the worktree.

The kind cluster was handed to #49's thread by cross-session message. This worktree still owns it until `make kind-down` runs here.

Offline checks: `make test-config` on this branch (result in the PR). The #88 optional nits (module docstring, decorator assertion) are deliberately not applied here, because `test_python37_case.py` is hashed into the case evidence. Apply them with the next change that reruns the case.

## Decisions and next steps

On 2026-10-13 Al adopted the lighter qualification path: matrix rows carry `evidence: image-only | live`, and only `live` counts as qualified. Both rows carry `qualification.evidence: live` (schema from #92), and selection of the 3.7 row reports `live`. Al says "merge".

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then SPEC-0046, PLAN-0050 and this handoff. Inspect git state. After #94 merges, no work remains in PLAN-0050; a 3.7 case's dependency setup belongs to the environment agent. Do not rerun live gates for a records-only change.
```
