---
id: HANDOFF-0117
kind: handoff
title: Candidate-free investigations reconciled with PR 123
status: recorded
updated: 2026-10-13
related: [ISSUE-0008, PLAN-0087, PLAN-0079, SPEC-0040]
---

# Candidate-free investigations reconciled with PR 123

## Verified state

Branch `claude/candidate-free-investigations-p0i38b`: main `1815f75` plus open PR #123 (head `f287f16`, "Fix-free runs"), plus this follow-up. Resolve the follow-up commit from Git. It merges after #123; until then its diff against main also shows #123's three commits.

#123 already implements [ISSUE-0008](../issues/ISSUE-0008-fix-free-product-investigation.md)'s slice through existing contracts: `build` acquires and sets up only the baseline without `fixed_revision`, `run_chain` runs only the revisions the case names, the gate gets empty candidate evidence and already permits fix `not_applicable` only, `admit` rejects any other fix claim, and durable mode runs the same `run_chain`. Reproduced offline: on main the corpus negatives `ih-python-healthcheck` and `ih-python-queryhelper` refuse with "names no fixed revision"; with #123 they build baseline-only investigations; paired `ih-python-pathtraversal` still builds both revisions.

The follow-up changes no gate, admission, prompt or production rule. It adds:

- gate rows without a candidate: safe baseline `not_reproduced`; failed control and missing witness `inconclusive`, fix `not_applicable`;
- composition checks without a candidate: raised-exception (`not-exploitable`) and calibrated-absence (`not-exploitable-absent`) negatives admitted `not_reproduced / not_applicable` and labelled LIKELY_NOT_EXPLOITABLE; no witness and an uncalibrated absence stay INCONCLUSIVE; an assessor's `not_verified` claim is rejected and the gate's triple stands; a baseline run from other source stops at execution with no gate; the fixture CLI requests only development and baseline runs;
- `evals.fixture_e2e.run --without-fix` (`fixture_case(fix=False)`, `docker_case(fix=False)`, recorded as `runner.fix_commit`), so any fixture case can run as a request without a fix commit;
- the execution stage's ready line names the revisions that ran instead of "both revisions ran".

Why it is generic: the absence of a candidate is expressed only by which revisions a case names; nothing keys on a case, corpus id or expected verdict. Transfer: the corpus negatives (`healthcheck`, `queryhelper`) and the fixture negatives use different sources, issue text and safe behaviors (no file open, raised `ValueError`, calibrated absence); the same unchanged gate handles all of them.

## Validation and blockers

- `TERM=xterm TEST_WORKERS=4 make test-config`: 1,977 passed, 12 warnings, 91 s.
- `make eval AGENT=chain`: 5/5 clean; `make eval AGENT=assessment`: 54/54 clean, mean repeat agreement 1.0. The same two runs on main `1815f75` gave 5/5 and 54/54. Scripted only; results under the local `.runs/evals/` (not committed).
- Unrun: every live model and Docker attempt. This session cannot reach llm.almckay.io or RIG0 Docker.

The live assessment prompt shows only baseline items in the evidence inventory, and the skill already says to use `not_applicable` without a candidate. If a live assessor still claims `not_verified`, it is rejected and the gate's triple stands (tested). How often that happens is a separate live hypothesis. Measure it before changing any prompt.

Live Docker attempts at `8679af4` on RIG0 (2026-10-13, run by the campaign's live owner; model not shared; each run once with a fresh evidence path; cleanup confirmed; evidence under the branch worktree's `.runs` on RIG0, not committed):

| Attempt | Result |
| --- | --- |
| B1 fixture `not-exploitable-absent --without-fix` | admitted `completed / not_reproduced / not_applicable`, LIKELY_NOT_EXPLOITABLE (`fixture-e2e-docker/absent-without-fix-001`) |
| B2 fixture `exploitable --without-fix` | admitted `completed / reproduced / not_applicable`, LIKELY_EXPLOITABLE (`fixture-e2e-docker/exploitable-without-fix-001`) |
| B3 corpus `ih-python-healthcheck`, attempt 1 | ERROR at environment with 0 model requests: the provider returned 502 `upstream_unreachable` (infrastructure; the endpoint answered again minutes later). Preserved; one diagnosed rerun (attempt 2) recorded as its own attempt |
| B3 corpus `ih-python-healthcheck`, attempt 2 (the one diagnosed rerun) | INCONCLUSIVE, stopped at environment after 8 model requests; the candidate-free path never got past setup. The first draft was refused (`draft.ready.build_command: Tuple should have at least 1 item`: an interpreted project with nothing to build, empty build step); the correction produced 59,887 characters of reasoning and no final JSON, spending the single output retry. No admitted disposition, so the oracle was not opened. Both attempts used; no further run without a change. The empty-build-step contract gap is a general environment mechanism handed to lane 2, not fixed here |

## Decisions and next steps

Next bounded action, for the one live Docker/model owner, from a worktree at this branch's head after `uv sync --locked` (provider and image files as in the run kit):

```sh
# transfer negative (fixture, calibrated absence), expect completed / not_reproduced / not_applicable
PYTHONPATH=src:. .venv/bin/python -m evals.fixture_e2e.run --sandbox docker --images $W/.runs/images.json \
  --case not-exploitable-absent --without-fix --provider-config <provider.json> \
  --stage-profiles evals/fixture_e2e/stage-profiles.json --live identification,planning,authoring,assessment \
  --evidence $W/.runs/fixture-e2e-docker/absent-without-fix-001
# positive (fixture), expect reproduced / not_applicable
... same with --case exploitable --without-fix --evidence $W/.runs/fixture-e2e-docker/exploitable-without-fix-001
# independent corpus negative through the product entry; compare with the evaluator-only oracle afterwards
CORSAIR_IMAGES=$W/.runs/images.json uv run --locked corsair run \
  --issue-json $W/evals/corpus/issues/ih-python-healthcheck/issue.json --provider-config <provider.json> \
  --stage-profiles $W/evals/fixture_e2e/stage-profiles.json --evidence $W/.runs/investigations/ih-python-healthcheck-1
```

Each run happens once with a fresh evidence path. If a run ends INCONCLUSIVE because the planner names an exception the contained source never raises, that is the known planning route (HANDOFF-0107), not this change. When the live attempts agree, mark ISSUE-0008 resolved and tick PLAN-0087's candidate-free step. Merges stay on Al's per-PR word: #123 first, then this follow-up.

## Continuation prompt

```text
Read AGENTS.md, docs/development/CURRENT.md, PLAN-0087, ISSUE-0008 and HANDOFF-0117. Check whether PR #123 and the candidate-free follow-up merged; verify from Git. Run the three live Docker attempts in HANDOFF-0117 once each through the single live owner, keep every receipt, compare the healthcheck result with its evaluator-only oracle only after the run, and record the results in ISSUE-0008 and PLAN-0087. Do not change gates, admission or prompts to get a verdict. Write a new handoff.
```
