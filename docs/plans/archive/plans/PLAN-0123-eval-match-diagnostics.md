---
id: PLAN-0123
kind: plan
title: Typed isolated evaluation match diagnostics
status: implemented_focused_validation
updated: 2026-10-25
---
# Scope

Add a typed, non-promotional `match_kind` to each isolated evaluator report row.
The canonical `MatchKind` contract is publicly re-exported and has exactly these
wire values: `exact_match`, `candidate_exact_mismatch`, `control_mismatch`,
`no_valid_output`, and `operational_failure`.

The classifier is diagnostic-only. The existing `fixture_matches_oracle` exact
comparison remains the sole source of row `status`; `summarize` continues to
count those existing statuses without a new report writer or aggregate rule.
For producer outputs, a differing control payload takes precedence over a
candidate mismatch. Operational feedback takes diagnostic precedence. The old
absent typed output (`submission` or `review` is `None`) is the only abstention
handling in this scope and becomes `no_valid_output`. A valid auditor review
whose decision is not the oracle's exact decision is a
`candidate_exact_mismatch`. No fuzzy matching, semantic credit, oracle edit, or
producer-decision integration is included.

## Out of scope

This change does not modify frozen inputs, oracles, prompts, model settings,
producer behavior, workflow behavior, native evidence, disposition policy,
aggregate pass/fail meaning, or baseline promotion. An alternate candidate
payload remains a failing exact-match diagnostic whose semantic validity is
unknown and requires review. It does not establish non-exploitability or a
negative clearance.

## Focused validation performed

From this worktree, using only the parent root pinned virtual environment:

```bash
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH="/Users/al/git/corsair/.work/recommendations-20261025/worktrees/eval-match-diagnostics/src:/Users/al/git/corsair/.work/recommendations-20261025/worktrees/eval-match-diagnostics" \
/Users/al/git/corsair/.venv/bin/python -m pytest \
  --basetemp .work/pytest-eval-match-diagnostics \
  tests/unit/test_agent_evaluator.py tests/unit/test_expanded_evals.py tests/unit/test_evaluation.py
```

Result: **27 passed in 1.81s**. The deterministic unit cases cover all five
`match_kind` values. They also show that the unchanged exact status predicate
and status-based aggregate preserve six attempts, two passes, and four failures
for a mixed diagnostic set, including an operational-feedback output that still
has an exact typed submission.

```bash
/Users/al/git/corsair/.venv/bin/ruff check \
  src/corsair/contracts/evaluation.py \
  src/corsair/contracts/__init__.py \
  src/corsair/evaluation/agents.py \
  tests/unit/test_agent_evaluator.py
/Users/al/git/corsair/.venv/bin/ruff format --check \
  src/corsair/contracts/evaluation.py \
  src/corsair/contracts/__init__.py \
  src/corsair/evaluation/agents.py \
  tests/unit/test_agent_evaluator.py
PYTHONDONTWRITEBYTECODE=1 /Users/al/git/corsair/.venv/bin/ty check \
  --python /Users/al/git/corsair/.venv
```

Result: Ruff reported all checks passed and four files already formatted; `ty`
reported all checks passed. A direct pure-Python assertion also verified that
the existing `json.dumps` report path renders `MatchKind.EXACT_MATCH` as the
`"exact_match"` row value.

## Remaining gates

Not run in this branch: `just check` as an aggregate project gate; native Docker
and Temporal tests; live-provider isolated diagnostics; composed workflow
qualification; package build, installed-wheel resource loading, and privacy
package inspection; and exact-revision CI. Those gates remain for the parent
and must not be inferred from deterministic fixture tests or scripted outputs.

## Final implementation stage

The bounded implementation is complete. Final pinned Just/Ruff/ty/documentation checks passed; the physical-Mac complete suite passed 156 tests with zero skips. Native timing and qualification scope are recorded in the branch receipt. Earlier focused-test notes retain their original stage context; this section records the final native stage. Frozen inputs/pins were not changed. No cost or production readiness claim is made.
