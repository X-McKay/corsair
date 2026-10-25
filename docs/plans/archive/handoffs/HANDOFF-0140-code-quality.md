---
id: HANDOFF-0140
kind: handoff
title: Dead-code review, single-purpose functions, Ruff and ty
status: complete
updated: 2026-10-25
related: [PLAN-0107, HANDOFF-0139]
---

> Historical record. Commands, counts and status describe the recorded revision, not the current working tree. See [current work](../../README.md) for current guidance.

# Dead-code review, single-purpose functions, Ruff and ty

The `manus/re-design` branch retains the original ADK + Temporal pilot boundary. Read [code quality and review](../reviews/code-quality.md), [CLI reference](../../../reference/cli.md), and [CURRENT](../CURRENT-before-doc-reorganization.md) before further changes.

Removed confirmed dead/stale paths and state; replaced the 221-line CLI dispatcher with an 8-line dispatcher and named handlers; centralized lexical request loading and safe error formatting; split frozen isolated evaluation into focused functions; made raw evidence/client/model/event and optional SDK values accurately typed. The worker, observer/job schemas, prompts, datasets, native cancellation and immutable operation identity semantics are unchanged. Frozen files are read once and parsed from their verified bytes. No new mixin/framework was needed.

## Tooling

`make check` is the canonical lint/format/type gate and is invoked by GitHub CI. Ruff 0.17.2 includes unused-argument checks; ty 0.0.91 checks src/tests/evals with warnings as errors. All 33 initial ty diagnostics were fixed without broad ignores or runtime/test source exclusions. Ruff alone excludes frozen target fixtures to preserve their source hashes and line numbers. Exact CI actions checkout v7.0.1 and setup-uv v10.3.2 use Node24, replacing stale action runtimes.

## Exact final receipts

```bash
make check
DOCKER_HOST=unix:///run/user/1000/docker.sock \
CORSAIR_TEST_DOCKER=1 CORSAIR_TEST_TEMPORAL=1 \
CORSAIR_LIVE_CONFIG=.state/live.json \
uv run --locked --extra providers pytest -q -W error
```

**105 passed in 110.07 seconds**, no skips, warnings treated as errors. The suite includes real Docker/Temporal/native CLI processes, source/evidence safeguards, history replay, cancellation/restart, genuine scripted ADK composition, live-auditor smoke, frozen external scoring and a fresh installed-wheel test outside the checkout. `uv build` also produced the distribution/wheel successfully.

```bash
uv run --locked --extra providers python evals/evaluators/agents.py auditor \
  evals/datasets/auditor-dev.json --settings .state/live.json --repeats 3 \
  --output .runs/evaluations/round2-auditor-final.json
```

**6/6 passed**, six real model calls, 0 operational failures; all 12 evaluator lifecycle lines are JSON. Dataset digest: `e865d259995f2e31d971ba5e01a3b5a627fe02771a195436fb73203b927fe0ef`. Raw outputs, endpoints and credentials remain ignored, not committed.

Frozen source tar digest replay matches all four declared variants. Reviewed high-confidence dead-code and unused-argument scans are clean; SDK callbacks and Pydantic validators are retained intentionally. Added regressions cover exact verified-byte parsing, empty/missing/zero count totals, log-file failure JSON, SDK diagnostic provenance, new 0600 mirror files and isolated-evaluator oracle/accounting boundaries.

Five-repeat same-host microbenchmarks: 200 dataset loads median 0.185241 s before versus 0.174778 s after; 200 x 10,000 count totals median 0.088828 s before versus 0.081264 s after. File reads per request/oracle pair dropped 4 to 2. These are narrow local-path measurements, not overall agent latency claims.

## Remaining limits and next action

Live security-producer policy blocking and general hostile-interpreter attestation remain unresolved; neither was hidden or bypassed. Local artifact paths still do not survive host loss. Accuracy is fixture-level only. Freeze new datasets/config identities and run affected native/evaluation gates before expanding a model, observer, recipe or permission profile.
