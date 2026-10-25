---
id: HANDOFF-recommendation-eval-match-diagnostics
kind: handoff
title: Isolated evaluation match diagnostics
status: focused_validation_complete
updated: 2026-10-25
---
# Delivered scope

The isolated evaluator now adds a canonical public `MatchKind` enum value to
each row as `match_kind`. Values are `exact_match`,
`candidate_exact_mismatch`, `control_mismatch`, `no_valid_output`, and
`operational_failure`. Classification is non-promotional: it does not change
the existing exact `fixture_matches_oracle` status predicate or `summarize`
pass/fail totals, add fuzzy or semantic matching, edit oracles, or create a
second report writer.

`no_valid_output` is limited to the established absent typed output
(`submission`/`review` is `None`). It is not a new producer abstention decision
or producer-decision integration. Candidate payload alternatives remain exact
mismatches with unknown semantic validity pending review.

# Focused evidence

```bash
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH="/Users/al/git/corsair/.work/recommendations-20261025/worktrees/eval-match-diagnostics/src:/Users/al/git/corsair/.work/recommendations-20261025/worktrees/eval-match-diagnostics" \
/Users/al/git/corsair/.venv/bin/python -m pytest \
  --basetemp .work/pytest-eval-match-diagnostics \
  tests/unit/test_agent_evaluator.py tests/unit/test_expanded_evals.py tests/unit/test_evaluation.py
```

Result: **27 passed in 1.81s**. New deterministic unit inputs cover all five
match kinds, auditor decision mismatch classification, JSON report
serialization, and the legacy status total invariant (six rows: two pass, four
fail).

Pinned checks also passed:

```bash
/Users/al/git/corsair/.venv/bin/ruff check src/corsair/contracts/evaluation.py src/corsair/contracts/__init__.py src/corsair/evaluation/agents.py tests/unit/test_agent_evaluator.py
/Users/al/git/corsair/.venv/bin/ruff format --check src/corsair/contracts/evaluation.py src/corsair/contracts/__init__.py src/corsair/evaluation/agents.py tests/unit/test_agent_evaluator.py
PYTHONDONTWRITEBYTECODE=1 /Users/al/git/corsair/.venv/bin/ty check --python /Users/al/git/corsair/.venv
```

Ruff: all checks passed; four files already formatted. `ty`: all checks passed.

# Parent-required gates and limits

Unrun: aggregate `just check`; native Docker/Temporal tests; live-provider
isolated evaluations; composed evaluation; package build and installed-wheel
resource loading; privacy package inspection; and exact-revision CI. No native,
live-model, package, or full qualification claim follows from the focused pure
tests. No commit, push, merge, Git configuration, SDK/package installation,
model call, Docker call, or service call was performed.

## Final native qualification and publication boundary

Final source imports were asserted against this worktree while using the one immutable root environment. `nix develop --no-update-lock-file --command just check` and the full `just test-all -q -W error` gate passed **156 tests**, with zero skips. Tests include actual SDK workers, Docker, CLI processes and a fresh installed wheel; scripted agent fixtures remain distinguished from real inference. The [sanitized receipt](../../../../evals/baselines/qualifications/qualification-eval-match-diagnostics-2026-10-25.json) records precise scope and unknown cost. This is an independent PR against the recorded base; no main-branch merge is authorized. Exact pushed commit/CI results are external delivery receipts, not retroactively rewritten historical claims.
